package workbench

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/core"
)

func TestChineseCompositionAndKeyboard(t *testing.T) {
	a, _ := testApp(t)
	a.Active = Rename
	tt := ui.NewTester(a.View, 1280, 820)
	field, ok := tt.AccessByRole(ui.RoleTextField, "标签前缀")
	if !ok {
		t.Fatal("input not accessible")
	}
	b := field.Bounds
	tt.ClickAt(b.X+b.W/2, b.Y+b.H/2)
	tt.Key(ui.Ctrl, ui.KeyA)
	tt.Compose("中文", 2)
	if _, active := tt.TextCaret(); !active {
		t.Fatal("IME caret unavailable")
	}
	tt.Type("中文_")
	if a.Settings.Renaming.TagPrefix != "中文_" {
		t.Fatal(a.Settings.Renaming.TagPrefix)
	}
	tt.Key(0, ui.KeyTab)
	if err := tt.Click("收起"); err != nil {
		t.Fatal(err)
	}
	tt.Key(0, ui.KeySpace)
	if !a.Pages[Rename].SettingsOpen {
		t.Fatal("keyboard activation did not reopen settings")
	}
}

func TestMultipleFileDropAndClearDuringAdd(t *testing.T) {
	a, q := testApp(t)
	a.Active = Preprocess
	root := t.TempDir()
	var paths []string
	for _, name := range []string{"中文一", "含 空格二"} {
		p := filepath.Join(root, name)
		if err := os.Mkdir(p, 0755); err != nil {
			t.Fatal(err)
		}
		paths = append(paths, p)
	}
	tt := ui.NewTester(a.View, 1280, 820)
	if !tt.DropFiles(450, 350, paths...) {
		t.Fatal("drop zone rejected files")
	}
	pump(t, a, q, func() bool { return len(a.Pages[Preprocess].Rows) == 2 && !a.Pages[Preprocess].Scanning })
	a.AddPaths(paths)
	a.clear(Preprocess)
	// Wait for the async metadata result, which must not restore cleared entries.
	select {
	case f := <-q:
		f()
	case <-time.After(2 * time.Second):
		t.Fatal("add result missing")
	}
	if len(a.Pages[Preprocess].Rows) != 0 {
		t.Fatal("pending add resurrected cleared queue")
	}
}

func TestScaleWithLongSelectedRow(t *testing.T) {
	a, _ := testApp(t)
	a.Active = Preprocess
	p := a.Pages[Preprocess]
	p.Rows = []*Row{{ID: 1, Path: `C:\测试\HGLIST-0001 ` + strings.Repeat("较长的名称", 12), Target: `C:\测试\目标`, Tag: "中文标签", Status: core.Invalid, Message: "标签来源冲突，请选择", Detection: core.Detection{Origin: "conflict", NameTag: "名称标签", MarkerTag: "目录标签"}}}
	p.Selected = 0
	tt := ui.NewTester(a.View, 1000, 680)
	for _, scale := range []float32{1, 1.5, 2} {
		tt.SetScale(scale)
		if err := tt.Click("收起"); err != nil {
			t.Fatal(err)
		}
		if err := tt.Click("展开"); err != nil {
			t.Fatal(err)
		}
		if !tt.HasText("加入标签") {
			t.Fatal("missing action")
		}
	}
}

func TestPerformanceSmoke(t *testing.T) {
	if os.Getenv("MANYYASUO_PERFORMANCE") != "1" {
		t.Skip("set MANYYASUO_PERFORMANCE=1 for 100-directory/20,000-file smoke")
	}
	a, q := testApp(t)
	a.Active = Preprocess
	root := t.TempDir()
	paths := make([]string, 100)
	for i := range paths {
		paths[i] = filepath.Join(root, fmt.Sprintf("HGLIST-%04d", i))
		if err := os.Mkdir(paths[i], 0755); err != nil {
			t.Fatal(err)
		}
		for j := 0; j < 200; j++ {
			if err := os.WriteFile(filepath.Join(paths[i], fmt.Sprintf("file-%04d.bin", j)), []byte("x"), 0600); err != nil {
				t.Fatal(err)
			}
		}
	}
	a.addValidated(Preprocess, paths)
	tt := ui.NewTester(a.View, 1280, 820)
	a.scan(Preprocess)
	deadline := time.Now().Add(60 * time.Second)
	maxFrame := time.Duration(0)
	start := time.Now()
	for a.Pages[Preprocess].Scanning {
		now := time.Now()
		stacks := make(chan string, 1)
		watchdog := time.AfterFunc(400*time.Millisecond, func() {
			buf := make([]byte, 64*1024)
			stacks <- string(buf[:runtime.Stack(buf, true)])
		})
		select {
		case f := <-q:
			f()
		case <-time.After(time.Millisecond):
		}
		a.Active = (a.Active + 1) % 4
		tt.Frame()
		elapsed := time.Since(now)
		if !watchdog.Stop() {
			t.Log(<-stacks)
		}
		if elapsed > maxFrame {
			maxFrame = elapsed
		}
		if time.Now().After(deadline) {
			t.Fatal("scan timeout")
		}
	}
	if maxFrame > 500*time.Millisecond {
		t.Fatalf("UI blocked for %s", maxFrame)
	}
	for _, r := range a.Pages[Preprocess].Rows {
		if r.Size != "200 B" {
			t.Fatal(r.Size)
		}
	}
	t.Logf("100 directories / 20,000 files: scan=%s maximum UI frame=%s", time.Since(start), maxFrame)
}
