package workbench

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync/atomic"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/config"
	"manyyasuo/internal/core"
	"manyyasuo/internal/jobs"
	"manyyasuo/internal/sevenzip"
)

const (
	Compress = iota
	Preprocess
	Extract
	Rename
)

var titles = []string{"批量压缩", "加入标签", "批量解压", "提取标签"}
var navigationTitles = []string{"压缩", "加入标签", "解压", "提取标签"}

type Row struct {
	ID                                       uint64
	Path, Target, Tag, Status, Message, Size string
	Detection                                core.Detection
	Edited, Resolved, Details                bool
	Progress                                 float64
}
type Page struct {
	Rows, Ready                               []*Row
	List, ReadyList                           ui.ListState
	Selected, ReadySelected                   int
	Sequence, Unwrap, SettingsOpen, ReadyView bool
	StartNumber                               string
	Generation                                uint64
	AddEpoch                                  uint64
	Scanning                                  bool
	cancelScan                                context.CancelFunc
	Error                                     string
	ReadyError                                string
	ExecutablePath, ExecutableError           string
	ExecutableChecking                        bool
	ExecutableRevision                        uint64
}
type App struct {
	Store                                  *config.Store
	Settings                               config.Settings
	Pages                                  [4]*Page
	Active                                 int
	Window                                 *mygo.Window
	Coordinator                            jobs.Coordinator
	Runner                                 sevenzip.Runner
	Job                                    *jobs.Job
	JobPage                                int
	Progress                               float64
	Completed, FailedCount, CancelledCount int
	Status                                 string
	Paused, Closing, ShowPassword          bool
	nextID                                 uint64
	closed                                 atomic.Bool
	events                                 chan jobs.Event
	dispatch                               func(func())
	theme                                  *ui.Theme
}

func New(store *config.Store) *App {
	settings, err := store.Load()
	a := &App{Store: store, Settings: settings, Status: "就绪", JobPage: -1, events: make(chan jobs.Event, 128)}
	if err != nil {
		a.Status = err.Error()
	}
	for i := range a.Pages {
		a.Pages[i] = &Page{Selected: -1, ReadySelected: -1, StartNumber: "0001", Unwrap: i == Preprocess || i == Compress, SettingsOpen: i != Compress}
	}
	a.theme = ui.LightTheme()
	a.theme.Font = "Microsoft YaHei UI"
	a.theme.FontSize = 14
	a.theme.Radius = 10
	a.theme.Background = legacySurface
	a.theme.Surface = legacySurface
	a.theme.SurfaceHover = softHover
	a.theme.SurfacePressed = legacySurface
	a.theme.Border = legacyControlBorder
	a.theme.Danger = ui.RGB(173, 64, 60)
	a.theme.Warning = ui.RGB(139, 92, 18)
	a.theme.Success = ui.RGB(40, 112, 70)
	a.theme.Text = softText
	a.theme.TextMuted = softMuted
	a.theme.Accent = softAccent
	a.theme.AccentHover = softAccentHover
	a.theme.AccentPressed = softAccentPressed
	a.theme.AccentText = ui.RGB(255, 255, 255)
	a.theme.InactiveAccent = softAccent
	a.theme.Selection = softHover
	a.theme.Scrollbar = legacyControlBorder
	a.theme.ScrollbarWidth = 8
	a.theme.Focus = softAccent
	a.theme.FocusRingWidth = 2
	a.theme.FocusRingOffset = 2
	// Prefer an existing configured executable, then conventional installations.
	executable, _ := os.Executable()
	fromPath, _ := exec.LookPath("7z.exe")
	candidates := []string{fromPath, filepath.Join(filepath.Dir(executable), "7z.exe"), filepath.Join(os.Getenv("ProgramFiles"), "7-Zip", "7z.exe"), filepath.Join(os.Getenv("ProgramFiles(x86)"), "7-Zip", "7z.exe")}
	for _, p := range candidates {
		if sevenzip.ValidateExecutable(p) == nil {
			if a.Settings.Compression.SevenZip == "" {
				a.Settings.Compression.SevenZip = p
			}
			if a.Settings.Extraction.SevenZip == "" {
				a.Settings.Extraction.SevenZip = p
			}
			break
		}
	}
	return a
}
func (a *App) Attach(w *mygo.Window) {
	a.Window = w
	// Native caption colors are optional on older Windows versions; keep the
	// system frame and its controls when DWM does not support these attributes.
	_ = setNativeWindowColors(w.NativeHandle(), a.theme.Background, a.theme.Text)
	a.dispatch = func(fn func()) {
		if !a.closed.Load() {
			w.Update(func() {
				if !a.closed.Load() {
					fn()
				}
			})
		}
	}
	w.OnFileDrop(func(e *mygo.FileDropEvent) { a.AddPaths(e.Paths) })
	w.OnClose(func(e *mygo.CloseEvent) {
		if a.Job != nil {
			e.PreventDefault()
			a.requestClose()
			return
		}
		a.closeScans()
	})
	w.OnClosed(func() { a.closed.Store(true); a.closeScans() })
	a.checkExecutable(Compress)
	a.checkExecutable(Extract)
	go func() {
		for e := range a.events {
			if a.closed.Load() {
				return
			}
			ev := e
			a.post(func() { a.applyEvent(ev) })
		}
	}()
}
func (a *App) post(fn func()) {
	if a.dispatch != nil {
		a.dispatch(fn)
	}
}
func (a *App) closeScans() {
	for _, p := range a.Pages {
		if p.cancelScan != nil {
			p.cancelScan()
		}
	}
}
func (a *App) busy(page int) bool { return a.Job != nil && a.JobPage == page }
func (a *App) rows(page int) []*Row {
	p := a.Pages[page]
	if page == Compress && p.ReadyView {
		return p.Ready
	}
	return p.Rows
}
func (a *App) tagPrefix(page int) string {
	switch page {
	case Compress:
		return a.Settings.Compression.TagPrefix
	case Preprocess:
		return a.Settings.Preprocessing.TagPrefix
	case Extract:
		return a.Settings.Extraction.TagPrefix
	default:
		return a.Settings.Renaming.TagPrefix
	}
}
func (a *App) save() {
	if err := a.Store.Save(a.Settings); err != nil {
		a.Status = "设置保存失败：" + err.Error()
	} else {
		a.Status = "设置已保存"
	}
}
func (a *App) AddPaths(paths []string) {
	if len(paths) == 0 {
		return
	}
	page := a.Active
	if a.busy(page) {
		a.Status = "当前模块正在运行，暂不能修改队列"
		return
	}
	if page == Compress {
		a.Pages[page].ReadyView = false
	}
	epoch := a.Pages[page].AddEpoch
	// Metadata can block on network drives, so it is collected off the UI thread.
	go func() {
		var valid []string
		var errors []string
		for _, p := range paths {
			abs, err := filepath.Abs(p)
			if err != nil {
				continue
			}
			info, err := os.Stat(abs)
			if err != nil {
				errors = append(errors, filepath.Base(p)+"：无法读取")
				continue
			}
			if (page == Extract && info.IsDir()) || (page != Extract && !info.IsDir()) {
				errors = append(errors, filepath.Base(p)+"：类型不适用")
				continue
			}
			if core.IsReparse(abs) {
				errors = append(errors, filepath.Base(p)+"：跳过链接")
				continue
			}
			valid = append(valid, abs)
		}
		a.post(func() {
			if a.Pages[page].AddEpoch != epoch {
				return
			}
			if a.busy(page) {
				a.Status = "队列正在运行，添加已取消"
				return
			}
			a.addValidated(page, valid)
			a.scan(page)
			if len(errors) > 0 {
				a.Status = strings.Join(errors, "；")
			}
		})
	}()
}
func (a *App) addValidated(page int, paths []string) {
	p := a.Pages[page]
	seen := map[string]bool{}
	for _, r := range p.Rows {
		seen[core.PathKey(r.Path)] = true
	}
	for _, path := range paths {
		key := core.PathKey(path)
		if seen[key] {
			continue
		}
		seen[key] = true
		a.nextID++
		p.Rows = append(p.Rows, &Row{ID: a.nextID, Path: path, Status: "pending", Message: "等待分析", Size: "计算中…"})
	}
	sort.SliceStable(p.Rows, func(i, j int) bool {
		x, y := p.Rows[i].Path, p.Rows[j].Path
		if core.NaturalLess(filepath.Base(x), filepath.Base(y)) {
			return true
		}
		if core.NaturalLess(filepath.Base(y), filepath.Base(x)) {
			return false
		}
		return core.PathKey(x) < core.PathKey(y)
	})
	p.Selected = -1
}
func (a *App) choose() {
	page := a.Active
	go func() {
		paths, err := mygo.Dialog.Open(mygo.OpenDialogOptions{Parent: a.Window, Title: "添加到" + titles[page], Directory: page != Extract, Multiple: true})
		a.post(func() {
			if err != nil {
				a.Pages[page].Error = err.Error()
				return
			}
			old := a.Active
			a.Active = page
			a.AddPaths(paths)
			a.Active = old
		})
	}()
}
func (a *App) choosePath(destination *string, directory bool) {
	page := a.Active
	go func() {
		paths, err := mygo.Dialog.Open(mygo.OpenDialogOptions{Parent: a.Window, Title: "选择路径", Directory: directory})
		a.post(func() {
			if err != nil {
				a.Status = err.Error()
			} else if len(paths) > 0 {
				*destination = paths[0]
				a.save()
				if directory {
					a.scan(page)
				} else {
					a.checkExecutable(page)
				}
			}
		})
	}()
}
func (a *App) checkExecutable(page int) {
	p := a.Pages[page]
	path := a.Settings.Compression.SevenZip
	if page == Extract {
		path = a.Settings.Extraction.SevenZip
	}
	p.ExecutableRevision++
	revision := p.ExecutableRevision
	p.ExecutablePath, p.ExecutableError, p.ExecutableChecking = path, "", true
	go func() {
		err := sevenzip.ValidateExecutable(path)
		a.post(func() {
			if p.ExecutableRevision != revision {
				return
			}
			p.ExecutableChecking = false
			if err != nil {
				p.ExecutableError = err.Error()
			}
		})
	}()
}
func (a *App) remove(page int, id uint64) {
	if a.busy(page) {
		return
	}
	p := a.Pages[page]
	rows := a.rows(page)
	out := make([]*Row, 0, len(rows))
	for _, r := range rows {
		if r.ID != id {
			out = append(out, r)
		}
	}
	if page == Compress && p.ReadyView {
		p.Ready = out
		p.ReadySelected = -1
		p.ReadyError = ""
	} else {
		p.Rows = out
		p.Selected = -1
		a.scan(page)
	}
}

func (a *App) clearCompleted(page int) {
	if a.busy(page) {
		return
	}
	p := a.Pages[page]
	var keep []*Row
	for _, r := range a.rows(page) {
		if r.Status != core.Done {
			keep = append(keep, r)
		}
	}
	if page == Compress && p.ReadyView {
		p.Ready = keep
		p.ReadySelected = -1
		p.ReadyError = ""
	} else {
		p.Rows = keep
		p.Selected = -1
		a.scan(page)
	}
}

func (a *App) minimumNumber(page int) {
	p := a.Pages[page]
	minimum := ""
	for _, r := range p.Rows {
		n := core.LastNumber(filepath.Base(r.Path))
		if n != "" && (minimum == "" || core.NaturalLess(n, minimum)) {
			minimum = n
		}
	}
	if minimum != "" {
		p.StartNumber = minimum
		a.scan(page)
	}
}
func (a *App) clear(page int) {
	if a.busy(page) {
		return
	}
	p := a.Pages[page]
	p.AddEpoch++
	if page == Compress && p.ReadyView {
		p.Ready = nil
		p.ReadySelected = -1
		p.ReadyError = ""
	} else {
		if p.cancelScan != nil {
			p.cancelScan()
		}
		p.Generation++
		p.Scanning = false
		p.Rows = nil
		p.Selected = -1
		p.Error = ""
	}
}

type scanResult struct {
	ID                            uint64
	Detection                     core.Detection
	Target, Size, Status, Message string
}

func (a *App) scan(page int) {
	p := a.Pages[page]
	if a.busy(page) {
		return
	}
	if p.cancelScan != nil {
		p.cancelScan()
	}
	ctx, cancel := context.WithCancel(context.Background())
	p.cancelScan = cancel
	p.Generation++
	gen := p.Generation
	p.Scanning = true
	p.Error = ""
	rows := make([]Row, len(p.Rows))
	for i, r := range p.Rows {
		rows[i] = *r
	}
	prefix := a.tagPrefix(page)
	settings := a.Settings
	sequence, start, unwrap := p.Sequence, p.StartNumber, p.Unwrap
	_ = unwrap
	go func() {
		results := make([]scanResult, len(rows))
		sources := make([]string, len(rows))
		for i, r := range rows {
			sources[i] = r.Path
		}
		var targets []string
		var batchError error
		if sequence && (page == Compress || page == Preprocess) {
			filePrefix := settings.Preprocessing.Prefix
			if page == Compress {
				filePrefix = settings.Compression.Prefix
			}
			targets, batchError = core.SequenceTargets(sources, filePrefix, start)
		}
		var renamePreviews []core.Preview
		if page == Rename {
			renamePreviews = core.AnalyzeRenames(sources, core.Rules{TagPrefix: prefix, BlockTerms: settings.Renaming.BlockTerms})
		}
		var items []core.PreprocessItem
		for i, r := range rows {
			if ctx.Err() != nil {
				return
			}
			v := scanResult{ID: r.ID, Target: r.Path, Status: core.Ready, Message: "准备就绪", Size: r.Size}
			switch page {
			case Compress, Preprocess:
				v.Detection = core.DetectTag(r.Path, prefix)
				tag := v.Detection.Tag
				if r.Edited {
					tag = r.Tag
				}
				if sequence && batchError == nil {
					v.Target = targets[i]
				} else if page == Compress {
					if v.Detection.PreservedName == "" {
						v.Status = core.Invalid
						v.Message = "未找到编号，请启用顺序编号"
					} else {
						v.Target = filepath.Join(filepath.Dir(r.Path), v.Detection.PreservedName)
					}
				}
				if v.Detection.Conflict() && !r.Resolved && !r.Edited {
					v.Status = core.Invalid
					v.Message = "标签来源冲突，请选择"
				}
				items = append(items, core.PreprocessItem{Source: r.Path, Target: v.Target, Tag: tag})
				if page == Preprocess {
					size, err := core.FolderSize(ctx, r.Path)
					if err == nil {
						v.Size = core.FormatSize(size)
					} else {
						v.Size = "读取失败"
					}
				}
			case Rename:
				q := renamePreviews[i]
				v.Target = q.Target
				v.Status = q.Status
				v.Message = q.Message
			case Extract:
				v.Target = settings.Extraction.OutputDir
				if v.Target == "" {
					v.Target = filepath.Dir(r.Path)
				}
			}
			results[i] = v
		}
		if len(items) > 0 && batchError == nil {
			previews, err := core.AnalyzePreprocess(items)
			batchError = err
			for i, v := range previews {
				results[i].Target = v.Target
				if v.Status == core.Invalid {
					results[i].Status = v.Status
					results[i].Message = v.Message
				}
			}
		}
		a.post(func() {
			if ctx.Err() != nil || p.Generation != gen || a.busy(page) {
				return
			}
			p.Scanning = false
			if batchError != nil {
				p.Error = batchError.Error()
			}
			byID := map[uint64]scanResult{}
			for _, v := range results {
				byID[v.ID] = v
			}
			for _, r := range p.Rows {
				// Completed extraction results retain their actual output path and
				// status when other rows or settings trigger a new preview scan.
				if page == Extract && r.Status == core.Done {
					continue
				}
				v, ok := byID[r.ID]
				if !ok {
					continue
				}
				r.Detection = v.Detection
				if !r.Edited {
					r.Tag = v.Detection.Tag
				}
				r.Target = v.Target
				r.Status = v.Status
				r.Message = v.Message
				r.Size = v.Size
			}
		})
	}()
}
func (a *App) editTag(page int, r *Row, tag string) {
	r.Tag = tag
	r.Edited = true
	r.Resolved = true
	a.scan(page)
}
func (a *App) errorText(page int) string {
	return a.errorTextFor(page, a.Pages[page].ReadyView)
}

func (a *App) errorTextFor(page int, ready bool) string {
	p := a.Pages[page]
	stageError := p.Error
	if page == Compress && ready {
		stageError = p.ReadyError
	}
	if stageError != "" {
		return stageError
	}
	if page == Compress && ready {
		if err := sevenzip.ValidateExecutableName(a.Settings.Compression.SevenZip); err != nil {
			return err.Error()
		}
		if _, _, err := sevenzip.CompressionArgs("preview", a.Settings.Compression); err != nil {
			return err.Error()
		}
	}
	if page == Extract {
		if err := sevenzip.ValidateExecutableName(a.Settings.Extraction.SevenZip); err != nil {
			return err.Error()
		}
	}
	if page == Extract || (page == Compress && ready) {
		if p.ExecutableChecking {
			return "正在检查 7-Zip 路径…"
		}
		if p.ExecutableError != "" {
			return p.ExecutableError
		}
	}
	return ""
}
func statusText(s string) string {
	switch s {
	case core.Done:
		return "已完成"
	case core.Failed:
		return "失败 · 可重试"
	case core.Invalid:
		return "需处理"
	case core.Cancelled:
		return "已取消"
	case "running":
		return "处理中"
	case core.Protected:
		return "保护原名"
	case core.NoTag:
		return "无标签"
	case core.AlreadyNamed:
		return "无需改名"
	default:
		return "待处理"
	}
}
func (a *App) selected(page int) *Row {
	p := a.Pages[page]
	i := p.Selected
	if page == Compress && p.ReadyView {
		i = p.ReadySelected
	}
	rows := a.rows(page)
	if i < 0 || i >= len(rows) {
		return nil
	}
	return rows[i]
}
func (a *App) requestClose() {
	if a.Closing {
		return
	}
	go func() {
		answer, err := mygo.Dialog.Message(mygo.MessageOptions{Parent: a.Window, Type: mygo.MessageQuestion, Title: "退出程序", Message: "当前任务尚未结束，停止任务并退出？", Detail: "会等待进程停止和文件恢复完成。", Buttons: []string{"继续工作", "停止并退出"}, CancelButton: 0})
		a.post(func() {
			if err != nil {
				a.Status = err.Error()
				return
			}
			if answer.Button != 1 {
				return
			}
			a.Closing = true
			a.closeScans()
			if a.Job != nil {
				a.Job.Cancel()
				a.Status = "正在停止任务并等待恢复…"
			} else {
				a.Window.Destroy()
			}
		})
	}()
}
func (a *App) cancel() {
	if a.Job == nil {
		return
	}
	go func() {
		answer, err := mygo.Dialog.Message(mygo.MessageOptions{Parent: a.Window, Type: mygo.MessageQuestion, Title: "取消任务", Message: "停止当前任务并取消剩余队列？", Detail: "已完成的更改会保留；解压产生的部分文件不会删除。", Buttons: []string{"继续任务", "取消任务"}, CancelButton: 0})
		a.post(func() {
			if err == nil && answer.Button == 1 && a.Job != nil {
				a.Job.Cancel()
				a.Status = "正在取消…"
			}
		})
	}()
}
func (a *App) pause() {
	if a.Job == nil {
		return
	}
	next := !a.Paused
	if err := a.Runner.Pause(next); err != nil {
		a.Status = err.Error()
		return
	}
	a.Paused = next
	a.Status = "队列继续运行"
	if next {
		a.Status = "队列已暂停"
	}
}
func (a *App) summary() string {
	if a.Job == nil {
		return "就绪"
	}
	return fmt.Sprintf("%s · %.0f%%", titles[a.JobPage], a.Progress*100)
}
