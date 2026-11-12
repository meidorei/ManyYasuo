package workbench

import (
	"fmt"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/core"
)

func clickUI(t *testing.T, tt *ui.Tester, label string) {
	t.Helper()
	if err := tt.Click(label); err != nil {
		t.Fatal(err)
	}
	tt.Advance(250 * time.Millisecond)
}
func visibleControl(t *testing.T, tt *ui.Tester, role ui.Role, name string, width, height int) ui.AccessInfo {
	t.Helper()
	n, ok := tt.AccessByRole(role, name)
	b := n.Bounds
	if !ok || n.Offscreen || b.W <= 0 || b.H <= 0 || b.X < 0 || b.Y < 0 || b.X+b.W > float32(width)+1 || b.Y+b.H > float32(height)+1 {
		t.Fatalf("control %q is not visible: %+v", name, n)
	}
	return n
}
func seedLayoutRows(a *App, page int) {
	p := a.Pages[page]
	// These are rendering fixtures only; no executable is launched.
	a.Settings.Compression.SevenZip = `C:\Program Files\7-Zip\7z.exe`
	a.Settings.Extraction.SevenZip = a.Settings.Compression.SevenZip
	for i := 0; i < 20; i++ {
		p.Rows = append(p.Rows, &Row{ID: uint64(i + 1), Path: fmt.Sprintf(`D:\工作文件\HGLIST-%04d`, i+1), Target: fmt.Sprintf(`D:\工作文件\HGLIST-%04d 示例标签`, i+1), Tag: "示例标签", Size: "125.6 MB", Status: core.Ready, Message: "准备就绪"})
	}
	p.Selected = 0
}
func saveLayoutPreview(t *testing.T, tt *ui.Tester, name string) {
	t.Helper()
	dir := os.Getenv("MANYYASUO_RENDER_DIR")
	if dir == "" {
		return
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatal(err)
	}
	f, err := os.Create(filepath.Join(dir, name+".png"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := png.Encode(f, tt.Image()); err != nil {
		t.Fatal(err)
	}
}
func TestLegacyConfigurationRetainsValuesAndKeyboardFocus(t *testing.T) {
	for page, title := range navigationTitles {
		t.Run(title, func(t *testing.T) {
			a, q := testApp(t)
			a.Active = page
			p := a.Pages[page]
			tt := ui.NewTester(a.View, 1360, 820)
			if !p.SettingsOpen {
				clickUI(t, tt, "展开")
			}
			before, generation := a.Settings, p.Generation
			field := "标签前缀"
			visibleControl(t, tt, ui.RoleTextField, field, 1360, 820)
			clickUI(t, tt, "收起")
			if _, ok := tt.AccessByRole(ui.RoleTextField, field); ok {
				t.Fatal("hidden settings remain accessible")
			}
			tt.Key(0, ui.KeySpace)
			tt.Frame()
			if !p.SettingsOpen {
				t.Fatal("keyboard activation lost after label change")
			}
			visibleControl(t, tt, ui.RoleTextField, field, 1360, 820)
			clickUI(t, tt, "收起")
			other := (page + 1) % 4
			clickUI(t, tt, navigationTitles[other])
			clickUI(t, tt, title)
			if p.SettingsOpen {
				t.Fatal("page switch reset disclosure state")
			}
			if a.Settings != before || p.Generation != generation || len(q) != 0 {
				t.Fatal("collapse changed values or scanned files")
			}
			if _, err := os.Stat(a.Store.Path); !os.IsNotExist(err) {
				t.Fatal("collapse saved configuration")
			}
		})
	}
}
func TestLegacySettingsKeepEdits(t *testing.T) {
	a, _ := testApp(t)
	tt := ui.NewTester(a.View, 1360, 820)
	clickUI(t, tt, "展开")
	f := visibleControl(t, tt, ui.RoleTextField, "后缀", 1360, 820)
	tt.ClickAt(f.Bounds.X+10, f.Bounds.Y+10)
	tt.Key(ui.Ctrl, ui.KeyA)
	tt.Type(".7z")
	clickUI(t, tt, "收起")
	clickUI(t, tt, "展开")
	if a.Settings.Compression.Extension != ".7z" {
		t.Fatal("configuration value reset")
	}
}
func TestBothCompressionQueuesRemainIndependent(t *testing.T) {
	a, _ := testApp(t)
	p := a.Pages[Compress]
	p.Rows = []*Row{{ID: 1, Path: `D:\input`, Target: `D:\input`, Status: core.Ready}}
	p.Ready = []*Row{{ID: 2, Path: `D:\ready`, Target: `D:\ready`, Status: core.Done}}
	tt := ui.NewTester(a.View, 1360, 820)
	if !tt.HasText("input") || !tt.HasText("ready") {
		t.Fatal("both stages must be visible together")
	}
	clickUI(t, tt, "清除已完成")
	if len(p.Ready) != 0 || len(p.Rows) != 1 {
		t.Fatal("clearing ready queue affected import queue")
	}
	p.Ready = []*Row{{ID: 3, Path: `D:\ready2`, Target: `D:\ready2`, Status: core.Ready}}
	tt.Frame()
	clickUI(t, tt, "清空")
	if len(p.Rows) != 0 || len(p.Ready) != 1 {
		t.Fatal("clearing import queue affected ready queue")
	}
}

func TestCompressionButtonsStartTheirOwnStage(t *testing.T) {
	a, q := testApp(t)
	source := filepath.Join(t.TempDir(), "HGLIST-0001 标签")
	if err := os.Mkdir(source, 0755); err != nil {
		t.Fatal(err)
	}
	a.addValidated(Compress, []string{source})
	a.scan(Compress)
	pump(t, a, q, func() bool { return !a.Pages[Compress].Scanning })
	tt := ui.NewTester(a.View, 1360, 820)
	clickUI(t, tt, "加入队列")
	if a.Job == nil || a.Pages[Compress].ReadyView {
		t.Fatal("enqueue did not start preparation")
	}
	pump(t, a, q, func() bool { return a.Job == nil })
	p := a.Pages[Compress]
	if len(p.Rows) != 0 || len(p.Ready) != 1 {
		t.Fatal("preparation did not transfer the item")
	}
	// A deliberately unavailable executable lets us assert stage routing
	// without invoking 7-Zip or changing the prepared folder.
	a.Settings.Compression.SevenZip = filepath.Join(t.TempDir(), "7z.exe")
	p.ReadyView = false
	tt.Frame()
	clickUI(t, tt, "开始压缩")
	if a.Job == nil || !p.ReadyView {
		t.Fatal("compression button reused the import stage")
	}
	pump(t, a, q, func() bool { return a.Job == nil })
	if len(p.Ready) != 1 || p.Ready[0].Path == "" {
		t.Fatal("failed compression discarded its queued item")
	}
}
func TestLegacyRunningControlsAndPageIsolation(t *testing.T) {
	a, _ := testApp(t)
	a.Active = Rename
	job, err := a.Coordinator.Start("UI test")
	if err != nil {
		t.Fatal(err)
	}
	defer a.Coordinator.Finish(job)
	a.Job, a.JobPage = job, Rename
	tt := ui.NewTester(a.View, 1080, 680)
	f := visibleControl(t, tt, ui.RoleTextField, "标签前缀", 1080, 680)
	if !f.Disabled {
		t.Fatal("running parameters are editable")
	}
	clickUI(t, tt, "收起")
	clickUI(t, tt, "加入标签")
	f = visibleControl(t, tt, ui.RoleTextField, "标签前缀", 1080, 680)
	if f.Disabled || a.Job != job {
		t.Fatal("switching modules interrupted job or disabled preparation")
	}
	visibleControl(t, tt, ui.RoleButton, "取消", 1080, 680)
}
func TestLegacyLayoutMatrix(t *testing.T) {
	for page := range titles {
		for _, size := range [][2]int{{1360, 820}, {1080, 680}} {
			for _, scale := range []float32{1, 1.5, 2} {
				name := fmt.Sprintf("page-%d-%dx%d-scale-%g", page, size[0], size[1], scale)
				t.Run(name, func(t *testing.T) {
					a, _ := testApp(t)
					a.Active = page
					tt := ui.NewTester(a.View, size[0], size[1])
					tt.SetScale(scale)
					primary := "执行：" + []string{"开始压缩", "加入标签", "开始解压", "提取标签"}[page]
					visibleControl(t, tt, ui.RoleButton, primary, size[0], size[1])
					if page == Compress {
						visibleControl(t, tt, ui.RoleButton, "加入队列", size[0], size[1])
					}
					saveLayoutPreview(t, tt, name+"-empty")
					seedLayoutRows(a, page)
					if page == Compress {
						a.Pages[page].Ready = []*Row{{ID: 100, Path: `D:\待压缩\示例`, Target: `D:\示例.7z`, Status: core.Ready}}
					}
					tt.Frame()
					saveLayoutPreview(t, tt, name)
					if !a.Pages[page].SettingsOpen {
						clickUI(t, tt, "展开")
					}
					visibleControl(t, tt, ui.RoleButton, primary, size[0], size[1])
					if page == Compress {
						name := "编辑标签 " + filepath.Base(a.Pages[page].Rows[0].Path)
						rowInput := visibleControl(t, tt, ui.RoleTextField, name, size[0], size[1])
						if rowInput.Bounds.H < 36 {
							t.Fatal("expanded configuration clips the first queue input", rowInput.Bounds)
						}
					}
					field := visibleControl(t, tt, ui.RoleTextField, "标签前缀", size[0], size[1])
					tt.ClickAt(field.Bounds.X+10, field.Bounds.Y+field.Bounds.H/2)
					if !tt.Focused("标签前缀") {
						t.Fatal("visible configuration field cannot receive focus")
					}
					if scale == 1 {
						saveLayoutPreview(t, tt, name+"-settings")
					}
					clickUI(t, tt, "收起")
					visibleControl(t, tt, ui.RoleButton, primary, size[0], size[1])
					if _, ok := tt.AccessByRole(ui.RoleTextField, "标签前缀"); ok {
						t.Fatal("collapsed configuration retained a hidden focus target")
					}
				})
			}
		}
	}
}
func TestLegacyLongNamesConflictsAndErrors(t *testing.T) {
	for _, page := range []int{Compress, Preprocess, Extract, Rename} {
		t.Run(titles[page], func(t *testing.T) {
			a, _ := testApp(t)
			a.Active = page
			seedLayoutRows(a, page)
			r := a.Pages[page].Rows[0]
			r.Path += strings.Repeat("很长的中文文件名", 30)
			r.Target = r.Path + " 目标"
			r.Status, r.Message = core.Invalid, "标签来源冲突，请选择"
			r.Detection = core.Detection{Origin: "conflict", NameTag: "名称", MarkerTag: "目录"}
			tt := ui.NewTester(a.View, 1080, 680)
			if !tt.HasText(r.Message) {
				t.Fatal("error hidden")
			}
			if page == Compress || page == Preprocess {
				visibleControl(t, tt, ui.RoleButton, "用名称标签", 1080, 680)
				visibleControl(t, tt, ui.RoleButton, "用目录标签", 1080, 680)
			}
			n, ok := tt.AccessByRole(ui.RoleText, filepath.Base(r.Path))
			if !ok || n.Bounds.H > 50 {
				t.Fatalf("long filename grew text: %+v", n.Bounds)
			}
			saveLayoutPreview(t, tt, fmt.Sprintf("page-%d-conflict", page))
		})
	}
}
