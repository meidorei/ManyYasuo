package sevenzip

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"manyyasuo/internal/config"
	"manyyasuo/internal/core"
)

type Runner struct {
	mu     sync.Mutex
	cmd    *exec.Cmd
	paused bool
}
type Outcome struct{ Path, Message string }

var percent = regexp.MustCompile(`([0-9]{1,3})%`)
var amount = regexp.MustCompile(`(?i)^[0-9]+\s*(KB|MB|GB|k|m|g)?$`)

func normalizeAmount(s string) string {
	r := strings.NewReplacer(" ", "", "kb", "k", "mb", "m", "gb", "g")
	return r.Replace(strings.ToLower(s))
}
func ValidateExecutableName(path string) error {
	if !strings.EqualFold(filepath.Base(path), "7z.exe") {
		return fmt.Errorf("请选择控制台版 7z.exe")
	}
	return nil
}
func ValidateExecutable(path string) error {
	if err := ValidateExecutableName(path); err != nil {
		return err
	}
	st, err := os.Stat(path)
	if err != nil || st.IsDir() {
		return fmt.Errorf("未找到有效的 7z.exe")
	}
	return nil
}
func CompressionArgs(source string, o config.Compression) ([]string, string, error) {
	ext := strings.TrimSpace(o.Extension)
	if ext == "" {
		ext = ".1"
	}
	if !strings.HasPrefix(ext, ".") {
		ext = "." + ext
	}
	if strings.ContainsAny(ext, `\/:*?"<>|`) {
		return nil, "", fmt.Errorf("扩展名包含非法字符")
	}
	level := strings.Split(o.Level, "-")[0]
	n, err := strconv.Atoi(level)
	if err != nil || n < 0 || n > 9 {
		return nil, "", fmt.Errorf("压缩等级必须为 0–9")
	}
	if !amount.MatchString(o.Dictionary) {
		return nil, "", fmt.Errorf("字典大小无效")
	}
	if _, err := strconv.Atoi(o.Word); err != nil {
		return nil, "", fmt.Errorf("单词大小无效")
	}
	solid := normalizeAmount(o.Solid)
	if o.Solid == "关闭" || o.Solid == "非固实" {
		solid = "off"
	}
	if o.Solid == "固实" {
		solid = "on"
	}
	if solid != "off" && solid != "on" && !amount.MatchString(o.Solid) {
		return nil, "", fmt.Errorf("固实块大小无效")
	}
	archive := source + ext
	args := []string{"a", archive, source, "-t7z", "-bsp1", "-m0=lzma2", "-mx=" + level, "-md=" + normalizeAmount(o.Dictionary), "-mfb=" + o.Word, "-ms=" + solid, "-sccUTF-8"}
	if o.Threads != "" && o.Threads != "自动" {
		n, err := strconv.Atoi(o.Threads)
		if err != nil || n < 1 {
			return nil, "", fmt.Errorf("线程数无效")
		}
		args = append(args, "-mmt="+o.Threads)
	}
	if o.Password != "" {
		args = append(args, "-p"+o.Password)
		if o.HideName {
			args = append(args, "-mhe=on")
		}
	}
	return args, archive, nil
}
func (r *Runner) Pause(paused bool) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.cmd != nil && r.cmd.Process != nil {
		if err := pauseProcess(r.cmd.Process, paused); err != nil {
			return err
		}
	}
	r.paused = paused
	return nil
}
func (r *Runner) Reset() { r.mu.Lock(); r.paused = false; r.mu.Unlock() }
func (r *Runner) wait(ctx context.Context) error {
	for {
		r.mu.Lock()
		p := r.paused
		r.mu.Unlock()
		if !p {
			return ctx.Err()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(50 * time.Millisecond):
		}
	}
}

// boundedOutput handles both CR progress lines and arbitrarily split UTF-8.
// No command line is logged, since it may contain a password.
type boundedOutput struct {
	mu       sync.Mutex
	tail     string
	last     int
	emitted  time.Time
	progress func(float64)
}

func (b *boundedOutput) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.tail += string(p)
	if len(b.tail) > 4096 {
		b.tail = b.tail[len(b.tail)-4096:]
	}
	matches := percent.FindAllStringSubmatch(b.tail, -1)
	if len(matches) > 0 {
		n, _ := strconv.Atoi(matches[len(matches)-1][1])
		if n > 100 {
			n = 100
		}
		if n != b.last && (n == 0 || n == 100 || time.Since(b.emitted) >= 100*time.Millisecond) {
			b.last = n
			b.emitted = time.Now()
			if b.progress != nil {
				b.progress(float64(n) / 100)
			}
		}
	}
	return len(p), nil
}
func (r *Runner) run(ctx context.Context, exe string, args []string, progress func(float64)) error {
	if err := r.wait(ctx); err != nil {
		return err
	}
	if err := ValidateExecutable(exe); err != nil {
		return err
	}
	cmd := exec.CommandContext(ctx, exe, args...)
	configureProcess(cmd)
	cmd.Stdin = nil
	out := &boundedOutput{last: -1, progress: progress}
	cmd.Stdout = out
	cmd.Stderr = out
	r.mu.Lock()
	if ctx.Err() != nil {
		r.mu.Unlock()
		return ctx.Err()
	}
	err := cmd.Start()
	if err == nil {
		r.cmd = cmd
		if r.paused {
			err = pauseProcess(cmd.Process, true)
			if err != nil {
				_ = cmd.Process.Kill()
			}
		}
	}
	r.mu.Unlock()
	if err != nil {
		if cmd.Process != nil {
			_ = cmd.Wait()
		}
		r.mu.Lock()
		r.cmd = nil
		r.mu.Unlock()
		return fmt.Errorf("无法启动 7-Zip：%w", err)
	}
	err = cmd.Wait()
	r.mu.Lock()
	r.cmd = nil
	r.mu.Unlock()
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if err != nil {
		if e, ok := err.(*exec.ExitError); ok {
			return fmt.Errorf("7-Zip 返回代码 %d；请检查密码、文件完整性、访问权限和磁盘空间", e.ExitCode())
		}
		return fmt.Errorf("7-Zip 执行失败：%w", err)
	}
	if progress != nil {
		progress(1)
	}
	return nil
}
func (r *Runner) Compress(ctx context.Context, source string, o config.Compression, progress func(float64)) (Outcome, error) {
	args, path, err := CompressionArgs(source, o)
	if err != nil {
		return Outcome{}, err
	}
	if core.IsReparse(source) {
		return Outcome{}, fmt.Errorf("不能压缩链接或无法读取的目录")
	}
	err = r.run(ctx, o.SevenZip, args, progress)
	out := Outcome{Path: path, Message: "压缩完成"}
	if err != nil {
		out.Message = "压缩未完成"
		if core.Exists(path) {
			out.Message += "；文件保留在 " + path
		}
	}
	return out, err
}
func (r *Runner) Extract(ctx context.Context, archive string, o config.Extraction, progress func(float64)) (Outcome, error) {
	parent := o.OutputDir
	if parent == "" {
		parent = filepath.Dir(archive)
	}
	if err := os.MkdirAll(parent, 0755); err != nil {
		return Outcome{}, err
	}
	stage, err := os.MkdirTemp(parent, ".jieya-*")
	if err != nil {
		return Outcome{}, err
	}
	args := []string{"x", archive, "-o" + stage, "-y", "-bsp1", "-bso1", "-bse1", "-sccUTF-8"}
	if o.Password != "" {
		args = append(args, "-p"+o.Password)
	}
	if err = r.run(ctx, o.SevenZip, args, progress); err == nil {
		var path, msg string
		path, msg, err = core.FinalizeExtraction(stage, parent, archive, core.Rules{TagPrefix: o.TagPrefix, BlockTerms: o.BlockTerms})
		if err == nil {
			return Outcome{path, msg}, nil
		}
	}
	kept := core.PreservePartial(stage, parent, core.ArchiveStem(archive))
	msg := "解压未完成"
	if kept != "" {
		msg += "；部分文件保存在 " + kept
	}
	return Outcome{kept, msg}, err
}

var _ io.Writer = (*boundedOutput)(nil)
