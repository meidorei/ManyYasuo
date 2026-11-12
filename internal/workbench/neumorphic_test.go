package workbench

import (
	"fmt"
	"math"
	"path/filepath"
	"testing"

	"github.com/egoist/mygo/ui"
)

func TestNeumorphicTextContrast(t *testing.T) {
	a, _ := testApp(t)
	luminance := func(c ui.Color) float64 {
		linear := func(v uint8) float64 {
			x := float64(v) / 255
			if x <= 0.04045 {
				return x / 12.92
			}
			return math.Pow((x+0.055)/1.055, 2.4)
		}
		return .2126*linear(c.R) + .7152*linear(c.G) + .0722*linear(c.B)
	}
	for _, pair := range []struct {
		name   string
		fg, bg ui.Color
	}{
		{"body", a.theme.Text, legacySurface},
		{"secondary", a.theme.TextMuted, legacySurface},
		{"emphasis", softAccentText, legacySurface},
		{"primary", a.theme.AccentText, a.theme.Accent},
		{"primary-hover", a.theme.AccentText, a.theme.AccentHover},
		{"primary-pressed", a.theme.AccentText, a.theme.AccentPressed},
		{"error", a.theme.Danger, legacySurface},
		{"warning", a.theme.Warning, legacySurface},
		{"success", a.theme.Success, legacySurface},
	} {
		x, y := luminance(pair.fg), luminance(pair.bg)
		contrast := (math.Max(x, y) + .05) / (math.Min(x, y) + .05)
		if contrast < 4.5 {
			t.Errorf("%s text contrast %.2f is below 4.5", pair.name, contrast)
		}
	}
}

func TestNeumorphicButtonStatesAndKeyboard(t *testing.T) {
	a, _ := testApp(t)
	disabled, clicks := false, 0
	tt := ui.NewTester(func(c *ui.Context) {
		c.SetTheme(a.theme)
		ui.Column(c).Fill().Background(legacySurface).Padding(24).Children(func() {
			primaryAction(c, "执行", disabled).Width(152).Height(40).OnClick(func() { clicks++ })
		})
	}, 240, 100)
	bounds := visibleControl(t, tt, ui.RoleButton, "执行", 240, 100).Bounds
	pixel := func() [4]uint32 {
		r, g, b, alpha := tt.Image().At(int(bounds.X+10), int(bounds.Y+bounds.H/2)).RGBA()
		return [4]uint32{r, g, b, alpha}
	}
	normal := pixel()
	saveLayoutPreview(t, tt, "control-primary-raised")
	tt.Move(bounds.X+bounds.W/2, bounds.Y+bounds.H/2)
	hover := pixel()
	tt.Press(bounds.X+bounds.W/2, bounds.Y+bounds.H/2)
	pressed := pixel()
	saveLayoutPreview(t, tt, "control-primary-pressed")
	if normal == hover || hover == pressed || normal == pressed {
		t.Fatal("normal, hover and pressed faces are not visually distinct")
	}
	if got := visibleControl(t, tt, ui.RoleButton, "执行", 240, 100).Bounds; got != bounds {
		t.Fatal("pressing changed button geometry", got, bounds)
	}
	tt.CancelPress()
	tt.Move(220, 80)
	tt.Key(0, ui.KeyTab)
	if !tt.Focused("执行") {
		t.Fatal("primary button is not keyboard focusable")
	}
	saveLayoutPreview(t, tt, "control-keyboard-focus")
	tt.Key(0, ui.KeySpace)
	if clicks != 1 {
		t.Fatal("keyboard did not activate primary button", clicks)
	}
	disabled = true
	tt.Frame()
	if !visibleControl(t, tt, ui.RoleButton, "执行", 240, 100).Disabled || pixel() == normal {
		t.Fatal("disabled button did not expose a distinct disabled state")
	}
	tt.ClickAt(bounds.X+bounds.W/2, bounds.Y+bounds.H/2)
	tt.Key(0, ui.KeySpace)
	if clicks != 1 {
		t.Fatal("disabled button still activated")
	}
}

func TestNeumorphicPreprocessColumnAlignment(t *testing.T) {
	for _, width := range []int{1080, 1360} {
		t.Run(fmt.Sprint(width), func(t *testing.T) {
			a, _ := testApp(t)
			a.Active = Preprocess
			seedLayoutRows(a, Preprocess)
			tt := ui.NewTester(a.View, width, 820)
			name := filepath.Base(a.Pages[Preprocess].Rows[0].Path)
			for _, pair := range []struct {
				header, cell string
				role         ui.Role
			}{
				{"当前名称", name, ui.RoleText},
				{"目标名称", filepath.Base(a.Pages[Preprocess].Rows[0].Target), ui.RoleText},
				{"编号", "切换顺序编号", ui.RoleButton},
				{"大小（点击复制）", "复制大小 " + name, ui.RoleButton},
				{"标签", "编辑标签 " + name, ui.RoleTextField},
				{"状态", "待处理", ui.RoleText},
			} {
				header := visibleControl(t, tt, ui.RoleText, pair.header, width, 820)
				cell := visibleControl(t, tt, pair.role, pair.cell, width, 820)
				if math.Abs(float64(header.Bounds.X-cell.Bounds.X)) > 2 {
					t.Errorf("column %s is misaligned: header=%v cell=%v", pair.header, header.Bounds, cell.Bounds)
				}
			}
		})
	}
}

func TestNeumorphicRunningLayouts(t *testing.T) {
	for page := range titles {
		for _, size := range [][2]int{{1080, 680}, {1360, 820}} {
			for _, scale := range []float32{1, 1.5, 2} {
				name := fmt.Sprintf("page-%d-%dx%d-scale-%g-running", page, size[0], size[1], scale)
				t.Run(name, func(t *testing.T) {
					a, _ := testApp(t)
					a.Active = page
					seedLayoutRows(a, page)
					p := a.Pages[page]
					if page == Compress {
						p.Ready, p.Rows, p.ReadyView = p.Rows, nil, true
					}
					job, err := a.Coordinator.Start(titles[page])
					if err != nil {
						t.Fatal(err)
					}
					defer a.Coordinator.Finish(job)
					a.Job, a.JobPage, a.Progress = job, page, .42
					a.Status = titles[page] + "正在运行"
					a.rows(page)[0].Status, a.rows(page)[0].Progress = "running", .42
					tt := ui.NewTester(a.View, size[0], size[1])
					tt.SetScale(scale)
					primary := "执行：" + []string{"开始压缩", "加入标签", "开始解压", "提取标签"}[page]
					if !visibleControl(t, tt, ui.RoleButton, primary, size[0], size[1]).Disabled {
						t.Fatal("running task allows a second start")
					}
					cancelLabel := "取消任务"
					if page == Preprocess {
						cancelLabel = "取消"
					}
					if visibleControl(t, tt, ui.RoleButton, cancelLabel, size[0], size[1]).Disabled {
						t.Fatal("running task cannot be cancelled")
					}
					saveLayoutPreview(t, tt, name)
					clickUI(t, tt, navigationTitles[(page+1)%4])
					if a.Job != job {
						t.Fatal("navigation interrupted the running task")
					}
				})
			}
		}
	}
}
