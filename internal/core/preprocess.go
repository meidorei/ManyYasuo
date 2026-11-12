package core

import (
	"context"
	"crypto/rand"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type PreprocessItem struct{ Source, Target, Tag, RemoveTag string }
type PreprocessOptions struct {
	TagPrefix string
	Unwrap    bool
}

func resolvedItems(items []PreprocessItem) []PreprocessItem {
	out := append([]PreprocessItem(nil), items...)
	for i := range out {
		p := &out[i]
		p.Source, _ = filepath.Abs(p.Source)
		if p.Target == "" {
			p.Target = p.Source
		}
		p.Target, _ = filepath.Abs(p.Target)
		if strings.TrimSpace(p.Tag) != "" && PathKey(p.Source) == PathKey(p.Target) {
			base, _ := SplitNumberedTag(filepath.Base(p.Source))
			if base != "" {
				p.Target = filepath.Join(filepath.Dir(p.Source), SanitizeName(base))
			}
		}
	}
	return out
}
func AnalyzePreprocess(items []PreprocessItem) ([]Preview, error) {
	items = resolvedItems(items)
	out := make([]Preview, len(items))
	sources, targets := map[string]bool{}, map[string]bool{}
	if len(items) == 0 {
		return out, fmt.Errorf("请先添加文件夹")
	}
	var first error
	for _, p := range items {
		if sources[PathKey(p.Source)] {
			first = fmt.Errorf("列表中存在重复文件夹")
		}
		sources[PathKey(p.Source)] = true
	}
	for i, p := range items {
		msg := ""
		info, err := os.Stat(p.Source)
		switch {
		case PathKey(filepath.Dir(p.Source)) != PathKey(filepath.Dir(p.Target)):
			msg = "目标文件夹必须与原文件夹位于同一目录"
		case SanitizeName(filepath.Base(p.Target)) != filepath.Base(p.Target):
			msg = "目标名称无效"
		case err != nil:
			msg = "文件夹不存在或无法读取"
		case !info.IsDir():
			msg = "不是文件夹"
		case IsReparse(p.Source):
			msg = "不能修改链接或重解析目录"
		case targets[PathKey(p.Target)]:
			msg = "生成了重复的目标路径"
		case Exists(p.Target) && !sources[PathKey(p.Target)]:
			msg = "目标已存在"
		}
		for _, other := range items {
			if PathKey(other.Source) != PathKey(p.Source) && strings.HasPrefix(PathKey(p.Source), PathKey(other.Source)+string(filepath.Separator)) {
				msg = "不能同时处理父目录及其子目录"
			}
		}
		targets[PathKey(p.Target)] = true
		status := Ready
		if msg != "" {
			status = Invalid
			if first == nil {
				first = fmt.Errorf("%s：%s", msg, p.Source)
			}
		} else {
			msg = "将处理为 " + filepath.Base(p.Target)
		}
		out[i] = Preview{Source: p.Source, Target: p.Target, Status: status, Message: msg}
	}
	return out, first
}
func tempName(parent string) string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	return filepath.Join(parent, fmt.Sprintf(".manyyasuo-%x.tmp", b))
}
func ExecutePreprocess(ctx context.Context, items []PreprocessItem, options PreprocessOptions) []Result {
	return executePreprocess(ctx, items, options, os.Rename)
}

// The two-phase rename supports cycles. Recovery reports actual locations even
// when a second filesystem failure prevents a complete rollback.
func executePreprocess(ctx context.Context, items []PreprocessItem, options PreprocessOptions, rename func(string, string) error) []Result {
	items = resolvedItems(items)
	previews, err := AnalyzePreprocess(items)
	results := make([]Result, len(items))
	for i, p := range items {
		results[i] = Result{Source: p.Source, Target: p.Source, Status: Cancelled, Message: "批次校验失败，未执行"}
	}
	if err != nil {
		for i, p := range previews {
			if p.Status == Invalid {
				results[i].Status = Invalid
				results[i].Message = p.Message
			}
		}
		if len(results) > 0 && results[0].Status == Cancelled {
			results[0].Status = Invalid
			results[0].Message = err.Error()
		}
		return results
	}
	if ctx.Err() != nil {
		for i := range results {
			results[i].Message = "已取消"
		}
		return results
	}
	locations, stages := make([]string, len(items)), make([]string, len(items))
	var staged, finalized []int
	for i, p := range items {
		locations[i] = p.Source
	}
	for i, p := range items {
		if PathKey(p.Source) == PathKey(p.Target) {
			continue
		}
		stage := tempName(filepath.Dir(p.Source))
		err = rename(p.Source, stage)
		if err != nil {
			break
		}
		locations[i] = stage
		stages[i] = stage
		staged = append(staged, i)
	}
	if err == nil {
		for _, i := range staged {
			if Exists(items[i].Target) {
				err = fmt.Errorf("目标在执行期间已被占用：%s", items[i].Target)
				break
			}
			err = rename(stages[i], items[i].Target)
			if err != nil {
				break
			}
			locations[i] = items[i].Target
			finalized = append(finalized, i)
		}
	}
	if err != nil {
		details := ""
		for j := len(finalized) - 1; j >= 0; j-- {
			i := finalized[j]
			if e := rename(locations[i], stages[i]); e != nil {
				details += "；回滚异常：" + e.Error()
			} else {
				locations[i] = stages[i]
			}
		}
		for j := len(staged) - 1; j >= 0; j-- {
			i := staged[j]
			if locations[i] != stages[i] {
				continue
			}
			if Exists(items[i].Source) {
				details += "；恢复路径被占用：" + items[i].Source
				continue
			}
			if e := rename(stages[i], items[i].Source); e != nil {
				details += "；恢复失败：" + e.Error()
			} else {
				locations[i] = items[i].Source
			}
		}
		for i, p := range items {
			message := fmt.Sprintf("批量重命名失败：%v%s", err, details)
			if locations[i] != p.Source {
				message += "；实际保留位置：" + locations[i]
			}
			results[i] = Result{p.Source, locations[i], Failed, message}
		}
		return results
	}
	for i, p := range items {
		results[i] = Result{p.Source, p.Target, Done, "已完成"}
		if ctx.Err() != nil {
			results[i].Status = Cancelled
			results[i].Message = "已取消；名称已整理，标签尚未处理"
			continue
		}
		e := prepareFolder(p, options)
		if e != nil {
			results[i].Status = Failed
			results[i].Message = "处理失败：" + e.Error()
		}
	}
	return results
}
func prepareFolder(p PreprocessItem, o PreprocessOptions) error {
	if o.Unwrap {
		if _, err := Unwrap(p.Target, o.TagPrefix); err != nil {
			return err
		}
	}
	tag, remove := strings.TrimSpace(p.Tag), strings.TrimSpace(p.RemoveTag)
	if tag != "" && remove != "" && !strings.EqualFold(tag, remove) {
		if err := RemoveEmptyMarker(p.Target, o.TagPrefix, remove); err != nil {
			return err
		}
	}
	if tag == "" {
		return nil
	}
	existing := FindMarker(p.Target, o.TagPrefix)
	if existing != "" && !strings.EqualFold(MarkerTag(existing, o.TagPrefix), tag) {
		if err := removeEmptyDir(existing); err != nil {
			return fmt.Errorf("旧标签目录非空或无法删除：%s：%w", existing, err)
		}
	}
	_, err := CreateMarker(p.Target, o.TagPrefix, tag)
	return err
}
