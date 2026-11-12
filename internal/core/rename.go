package core

import (
	"os"
	"path/filepath"
	"strings"
)

func AnalyzeRename(source string, rules Rules, reserved map[string]bool) Preview {
	source, _ = filepath.Abs(source)
	p := Preview{Source: source, Status: Invalid}
	info, err := os.Stat(source)
	if err != nil {
		p.Message = "文件夹不存在或无法读取"
		return p
	}
	if !info.IsDir() {
		p.Message = "不是文件夹"
		return p
	}
	if IsReparse(source) {
		p.Message = "不能修改链接或重解析目录"
		return p
	}
	if block := BlockingFile(source, BlockTerms(rules.BlockTerms)); block != "" {
		p.Status = Protected
		p.Message = "检测到“" + filepath.Base(block) + "”，保留原名"
		return p
	}
	marker := FindMarker(source, rules.TagPrefix)
	p.Tag = MarkerTag(marker, rules.TagPrefix)
	if p.Tag == "" {
		p.Status = NoTag
		p.Message = "未找到有效标签目录"
		return p
	}
	p.Marker, _ = filepath.Rel(source, marker)
	name := filepath.Base(source)
	clean := strings.ToLower(strings.TrimSpace(collisionSuffix.ReplaceAllString(name, "")))
	tag := strings.ToLower(p.Tag)
	if clean == tag || strings.HasSuffix(clean, " "+tag) {
		p.Status = AlreadyNamed
		p.Target = source
		p.Message = "名称已经正确"
		return p
	}
	base, _ := SplitNumberedTag(name)
	targetName := p.Tag
	if base != "" {
		targetName = base + " " + p.Tag
	}
	targetName = SanitizeName(targetName)
	if strings.EqualFold(targetName, name) {
		p.Status = AlreadyNamed
		p.Target = source
		p.Message = "名称已经正确"
		return p
	}
	p.Target = UniqueDestination(filepath.Dir(source), targetName, reserved)
	p.Status = Ready
	p.Message = "将改名为 " + filepath.Base(p.Target)
	return p
}
func AnalyzeRenames(sources []string, rules Rules) []Preview {
	reserved := map[string]bool{}
	out := make([]Preview, 0, len(sources))
	for _, s := range sources {
		p := AnalyzeRename(s, rules, reserved)
		if p.Status == Ready {
			reserved[PathKey(p.Target)] = true
		}
		out = append(out, p)
	}
	return out
}
func ExecuteRename(source string, rules Rules) Result {
	p := AnalyzeRename(source, rules, nil)
	r := Result{p.Source, p.Target, p.Status, p.Message}
	if p.Status != Ready {
		return r
	}
	if err := os.Rename(p.Source, p.Target); err != nil {
		r.Status = Failed
		r.Target = p.Source
		r.Message = "重命名失败：" + err.Error()
		return r
	}
	r.Status = Done
	r.Message = "已改名为 " + filepath.Base(p.Target)
	if err := removeEmptyDir(filepath.Join(p.Target, p.Marker)); err != nil {
		r.Message += " · 标签目录非空或无法删除，已保留"
	}
	return r
}
