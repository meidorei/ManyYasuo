package workbench

import (
	"fmt"
	"image/png"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/config"
	"manyyasuo/internal/core"
	"manyyasuo/internal/jobs"
)

func testApp(t *testing.T) (*App, chan func()) {
	t.Helper()
	a := New(&config.Store{Path: filepath.Join(t.TempDir(), "config.json")})
	q := make(chan func(), 1000)
	a.dispatch = func(f func()) { q <- f }
	t.Cleanup(a.closeScans)
	return a, q
}
func pump(t *testing.T, a *App, q chan func(), done func() bool) {
	t.Helper()
	deadline := time.NewTimer(15 * time.Second)
	defer deadline.Stop()
	for !done() {
		select {
		case f := <-q:
			f()
		case e := <-a.events:
			a.applyEvent(e)
		case <-deadline.C:
			t.Fatal("operation timed out")
		}
	}
}
func TestPagesAndLayout(t *testing.T) {
	a, _ := testApp(t)
	tt := ui.NewTester(a.View, 1280, 820)
	for _, title := range navigationTitles {
		if err := tt.Click(title); err != nil {
			t.Fatal(err)
		}
		if !tt.HasText(title) {
			t.Fatal(title)
		}
	}
	for _, scale := range []float32{1, 1.5, 2} {
		tt.SetScale(scale)
		tt.SetSize(1000, 680)
		if err := tt.Click("收起"); err != nil {
			t.Fatal(scale, err)
		}
		if err := tt.Click("展开"); err != nil {
			t.Fatal(scale, err)
		}
	}
}
func TestQueueIsolationDedupAndNaturalSort(t *testing.T) {
	a, _ := testApp(t)
	a.addValidated(Preprocess, []string{`C:\x\item-10`, `C:\x\item-2`, `C:\x\item-2`})
	if len(a.Pages[Preprocess].Rows) != 2 || filepath.Base(a.Pages[Preprocess].Rows[0].Path) != "item-2" {
		t.Fatal("sort or dedup")
	}
	if len(a.Pages[Compress].Rows) != 0 {
		t.Fatal("queue leaked")
	}
}

func TestExecutableValidationRejectsMissingAndStaleResults(t *testing.T) {
	a, q := testApp(t)
	a.Settings.Extraction.SevenZip = filepath.Join(t.TempDir(), "7z.exe")
	a.checkExecutable(Extract)
	pump(t, a, q, func() bool { return !a.Pages[Extract].ExecutableChecking })
	if a.errorText(Extract) == "" {
		t.Fatal("missing executable must disable extraction")
	}
	valid := filepath.Join(t.TempDir(), "7z.exe")
	if err := os.WriteFile(valid, nil, 0600); err != nil {
		t.Fatal(err)
	}
	a.checkExecutable(Extract)
	a.Settings.Extraction.SevenZip = valid
	a.checkExecutable(Extract)
	for i := 0; i < 2; i++ {
		select {
		case f := <-q:
			f()
		case <-time.After(5 * time.Second):
			t.Fatal("validation timed out")
		}
	}
	if a.errorText(Extract) != "" {
		t.Fatal("stale missing-path result replaced latest validation")
	}
}
func TestStaleScanAndManualTag(t *testing.T) {
	a, q := testApp(t)
	root := t.TempDir()
	p := filepath.Join(root, "HGLIST-0001 名称")
	_ = os.Mkdir(p, 0755)
	_, _ = core.CreateMarker(p, "AAA_", "目录")
	a.addValidated(Compress, []string{p})
	a.scan(Compress)
	pump(t, a, q, func() bool { return !a.Pages[Compress].Scanning })
	r := a.Pages[Compress].Rows[0]
	if !r.Detection.Conflict() || r.Status != core.Invalid {
		t.Fatal(r)
	}
	a.editTag(Compress, r, "手动标签")
	pump(t, a, q, func() bool { return !a.Pages[Compress].Scanning })
	if r.Tag != "手动标签" || r.Status != core.Ready {
		t.Fatal(r)
	}
	a.scan(Compress)
	a.clear(Compress)
	for len(q) > 0 {
		(<-q)()
	}
	if len(a.Pages[Compress].Rows) != 0 {
		t.Fatal("stale result restored cleared row")
	}
}
func TestPrepareCompressionAndMutualExclusion(t *testing.T) {
	a, q := testApp(t)
	path := filepath.Join(t.TempDir(), "HGLIST-0001 标签")
	_ = os.Mkdir(path, 0755)
	a.addValidated(Compress, []string{path})
	a.scan(Compress)
	pump(t, a, q, func() bool { return !a.Pages[Compress].Scanning })
	a.start()
	if a.Job == nil {
		t.Fatal(a.Pages[Compress].Error)
	}
	a.Active = Rename
	a.start()
	if a.JobPage != Compress {
		t.Fatal("second job started")
	}
	pump(t, a, q, func() bool { return a.Job == nil })
	if len(a.Pages[Compress].Rows) != 0 || len(a.Pages[Compress].Ready) != 1 {
		t.Fatal("preparation did not transfer row")
	}
	r := a.Pages[Compress].Ready[0]
	if !core.Exists(filepath.Join(r.Path, "AAA_标签")) {
		t.Fatal(r)
	}
}
func TestOldJobEventIgnored(t *testing.T) {
	a, _ := testApp(t)
	job, _ := a.Coordinator.Start("test")
	a.Job = job
	a.JobPage = Preprocess
	a.applyEvent(jobs.Event{JobID: job.ID + 1, Kind: "finished"})
	if a.Job == nil {
		t.Fatal("stale completion")
	}
	a.Coordinator.Finish(job)
}
func TestRenderPreviews(t *testing.T) {
	dir := os.Getenv("MANYYASUO_RENDER_DIR")
	if dir == "" {
		t.Skip("optional screenshot artifacts")
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatal(err)
	}
	a, _ := testApp(t)
	for page := range a.Pages {
		a.Active = page
		p := a.Pages[page]
		for i := 0; i < 12; i++ {
			a.nextID++
			p.Rows = append(p.Rows, &Row{ID: a.nextID, Path: fmt.Sprintf(`D:\工作文件\HGLIST-%04d`, i+1), Target: fmt.Sprintf(`D:\工作文件\HGLIST-%04d 示例标签`, i+1), Tag: "示例标签", Size: "125.6 MB", Status: core.Ready, Message: "准备就绪，可开始处理"})
		}
		p.Selected = 0
		tt := ui.NewTester(a.View, 1280, 820)
		f, err := os.Create(filepath.Join(dir, fmt.Sprintf("page-%d.png", page)))
		if err != nil {
			t.Fatal(err)
		}
		err = png.Encode(f, tt.Image())
		_ = f.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
}
