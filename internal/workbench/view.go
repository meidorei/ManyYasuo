package workbench

import (
	"fmt"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"

	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/core"
	"manyyasuo/internal/sevenzip"
)

func (a *App) View(c *ui.Context) {
	c.SetTheme(a.theme)
	ui.Column(c).Fill().Background(legacySurface).Children(func() {
		a.header(c)
		ui.Row(c).FillWidth().Grow(1).MinHeight(0).Children(func() {
			a.navigation(c)
			ui.Column(c.Key(a.Active)).Grow(1).MinWidth(0).FillHeight().Padding(8, 20, 20, 20).Gap(16).Children(func() {
				if a.Active == Compress {
					a.pipeline(c)
					a.settingsView(c)
				} else {
					a.settingsView(c)
					a.workspace(c)
				}
				a.footer(c)
			})
		})
	})
}
func (a *App) header(c *ui.Context) {
	ui.Row(c).FillWidth().Height(56).Shrink(0).Padding(12, 20).Gap(24).AlignItems(ui.Center).Children(func() {
		ui.Text(c, "文件工作台").FontSize(20).Bold()
		ui.Text(c, titles[a.Active]).FontSize(20).Bold().Grow(1)
		ui.Text(c, "批量处理 · 本地执行").FontSize(13).TextColor(a.theme.TextMuted)
	})
}
func (a *App) navigation(c *ui.Context) {
	ui.Column(c).Width(160).Shrink(0).FillHeight().Padding(12, 16, 0, 16).Gap(16).Children(func() {
		ui.Text(c, "处理模块").FontSize(12).TextColor(a.theme.TextMuted).Padding(0, 4, 8, 4)
		for i, title := range navigationTitles {
			page := i
			ui.Row(c.Key(i)).FillWidth().Gap(8).AlignItems(ui.Center).Children(func() {
				mark := ui.Column(c).Width(3).Height(20).Radius(1.5).AccessHidden(true)
				b := action(c.Key("nav"), title).Grow(1).Height(40).Justify(ui.Start).AccessSelected(a.Active == page)
				if page == a.Active {
					mark.Background(softAccent)
					recessed(b, 10).TextColor(softAccentText).Bold()
				}
				b.OnClick(func() {
					a.Active = page
					if a.Window != nil {
						a.Window.SetTitle(titles[page] + " · 文件工作台")
					}
				})
			})
		}
		ui.Column(c).Grow(1)
		recessed(ui.Column(c), 10).FillWidth().Padding(12).Children(func() {
			status, color := "空闲", a.theme.Success
			if a.Job != nil {
				status, color = navigationTitles[a.JobPage]+"中", softAccentText
			}
			ui.Text(c, "• "+status).FontSize(12).TextColor(color)
		}).Margin(0, 0, 20, 0)
	})
}

// The two visible compression panes share a job coordinator but never a list
// state. Select the operation's stage only at input time, not while rendering.
func (a *App) compressionAction(ready bool, fn func()) func() {
	return func() { a.Pages[Compress].ReadyView = ready; fn() }
}
func (a *App) pipeline(c *ui.Context) {
	p := a.Pages[Compress]
	locked := a.busy(Compress)
	ui.Row(c.Key("pipeline")).Grow(1).MinHeight(0).FillWidth().Gap(16).Children(func() {
		card(c.Key("import-pane")).Grow(1.12).FillHeight().Padding(20).Gap(16).Children(func() {
			ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
				ui.Text(c, "01").FontSize(13).Bold().TextColor(softAccentText)
				ui.Text(c, "导入文件夹").FontSize(16).Bold()
				ui.Text(c, queueCount(len(p.Rows))).FontSize(12).TextColor(a.theme.TextMuted)
			})
			ui.Row(c).FillWidth().Children(func() {
				action(c, "选择文件夹").Width(104).Disabled(locked).OnClick(a.choose)
				ui.Column(c).Grow(1)
				action(c, "清空").Width(58).Label("清空导入列表").Disabled(locked || len(p.Rows) == 0).OnClick(a.compressionAction(false, func() { a.clear(Compress) }))
			})
			ui.Row(c).FillWidth().Wrap().Gap(12).AlignItems(ui.Center).Children(func() {
				smallLabel(c, "起始编号")
				input(c.Key("start"), "起始编号", &p.StartNumber, locked, func() { a.scan(Compress) }).Width(78)
				action(c, "提取最小编号").Width(116).Disabled(locked).OnClick(func() { a.minimumNumber(Compress) })
			})
			a.queue(c, Compress, false)
		})
		ui.Column(c).Width(114).Shrink(0).FillHeight().Justify(ui.Center).Children(func() {
			action(c, "加入队列").FillWidth().Height(40).TextColor(softAccentText).Bold().Disabled(a.Job != nil || p.Scanning || len(p.Rows) == 0 || a.errorTextFor(Compress, false) != "").OnClick(a.compressionAction(false, a.start))
		})
		card(c.Key("ready-pane")).Grow(1).FillHeight().Padding(20).Gap(16).Children(func() {
			ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
				ui.Text(c, "02").FontSize(13).Bold().TextColor(softAccentText)
				ui.Text(c, "压缩队列").FontSize(16).Bold()
				ui.Text(c, queueCount(len(p.Ready))).FontSize(12).TextColor(a.theme.TextMuted)
			})
			ui.Row(c).FillWidth().Children(func() {
				quietAction(c, "清除已完成").Disabled(locked || len(p.Ready) == 0).OnClick(a.compressionAction(true, func() { a.clearCompleted(Compress) }))
			})
			a.queue(c, Compress, true)
		})
	})
}
func queueCount(n int) string {
	if n == 0 {
		return "队列为空"
	}
	return fmt.Sprintf("%d 项", n)
}
func (a *App) workspace(c *ui.Context) {
	page, p := a.Active, a.Pages[a.Active]
	locked := a.busy(page)
	card(c.Key("workspace")).FillWidth().Grow(1).MinHeight(0).Padding(20).Gap(12).Children(func() {
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			title := map[int]string{Preprocess: "文件夹列表", Extract: "解压队列", Rename: "提取标签预览"}[page]
			ui.Text(c, title).FontSize(16).Bold()
			ui.Text(c, queueCount(len(p.Rows))).FontSize(12).TextColor(a.theme.TextMuted).Grow(1)
			if page != Preprocess {
				label := "选择文件夹"
				if page == Extract {
					label = "选择压缩文件"
				}
				action(c, label).Disabled(locked).OnClick(a.choose)
			}
			action(c, "清空").Disabled(locked || len(p.Rows) == 0).OnClick(func() { a.clear(page) })
		})
		if page == Preprocess {
			a.preprocessColumns(c)
		}
		a.queue(c, page, false)
	})
}
func (a *App) queue(c *ui.Context, page int, ready bool) {
	p := a.Pages[page]
	rows, list := p.Rows, &p.List
	if ready {
		rows, list = p.Ready, &p.ReadyList
	}
	ui.Column(c.Key(fmt.Sprint("queue-region", ready))).FillWidth().Grow(1).MinHeight(0).Gap(8).Children(func() {
		if p.Scanning && !ready {
			ui.Text(c, "正在分析文件…").FontSize(12).TextColor(softAccentText)
		}
		if errorText := a.errorTextFor(page, ready); errorText != "" && len(rows) > 0 {
			ui.Text(c, errorText).FontSize(12).TextColor(a.theme.Danger).Wrap().FillWidth()
			if (page == Extract || (page == Compress && ready)) && a.sevenZipInvalid(page) {
				action(c, "打开 7-Zip 设置").OnClick(func() { p.SettingsOpen = true })
			}
		}
		if len(rows) == 0 {
			text := "拖入文件夹，或点击“选择文件夹”"
			if page == Compress {
				text = "拖入文件夹\n或点击上方“选择文件夹”"
			}
			if ready {
				text = "队列为空\n导入文件夹后，点击“加入队列”"
			}
			if page == Extract {
				text = "拖入压缩文件，或点击“选择压缩文件”"
			}
			zone := recessed(ui.Column(c.Key("drop-zone")), 12).FillWidth().Grow(1).MinHeight(0).Padding(12).Justify(ui.Center).Children(func() {
				ui.Text(c, text).FontSize(14).TextColor(a.theme.TextMuted).Wrap().FillWidth().TextAlign(ui.Center)
			})
			if paths := zone.DroppedFiles(); len(paths) > 0 {
				a.AddPaths(paths)
			}
			return
		}
		list.Selected = nil
		list.Key = func(i int) any { return rows[i].ID }
		list.Label = func(i int) string { return filepath.Base(rows[i].Path) }
		ui.List(c.Key("items"), list, len(rows), func(i int) {
			r := rows[i]
			ui.Column(c.Key(r.ID)).FillWidth().Padding(2, 4, 6, 4).Children(func() { a.queueRow(c, page, ready, r) })
		}).FillWidth().Grow(1).MinHeight(0)
	})
}
func (a *App) rowColor(r *Row) ui.Color {
	switch r.Status {
	case core.Invalid, core.Failed:
		return a.theme.Danger
	case core.Done, core.AlreadyNamed:
		return a.theme.Success
	case core.Protected, core.NoTag:
		return a.theme.Warning
	}
	return a.theme.TextMuted
}
func (a *App) removeRow(c *ui.Context, page int, ready bool, r *Row) {
	quietAction(c, "×").Width(preprocessRemoveWidth).Height(36).FontSize(17).Label("移除 " + filepath.Base(r.Path)).Tooltip("移除").Disabled(a.busy(page)).OnClick(func() {
		if page == Compress {
			a.Pages[page].ReadyView = ready
		}
		a.remove(page, r.ID)
	})
}
func (a *App) queueRow(c *ui.Context, page int, ready bool, r *Row) {
	locked := a.busy(page)
	row := ui.Column(c).FillWidth().Background(legacySurface).Radius(8).Border(1, softDivider).Padding(10).Gap(8)
	if row.Hovered() {
		row.Background(softHover)
	}
	row.Children(func() {
		if page == Preprocess {
			a.preprocessRow(c, r)
		} else if page == Compress && !ready {
			ui.Row(c).FillWidth().Gap(8).AlignItems(ui.Center).Children(func() {
				ui.Text(c, filepath.Base(r.Path)).SingleLine().Tooltip(r.Path).Grow(1).MinWidth(0).Bold()
				input(c.Key("tag"), "编辑标签 "+filepath.Base(r.Path), &r.Tag, locked, func() { a.editTag(page, r, r.Tag) }).Grow(1).MinWidth(50)
				a.removeRow(c, page, ready, r)
			})
		} else {
			ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
				ui.Column(c).Grow(1).MinWidth(0).Gap(4).Children(func() {
					ui.Text(c, filepath.Base(r.Path)).SingleLine().Tooltip(r.Path).Bold()
					ui.Text(c, filepath.Dir(r.Path)).SingleLine().Tooltip(r.Path).FontSize(12).TextColor(a.theme.TextMuted)
				})
				if page == Rename {
					ui.Text(c, "→").TextColor(a.theme.TextMuted)
					ui.Column(c).Grow(1).MinWidth(0).Gap(4).Children(func() {
						ui.Text(c, filepath.Base(r.Target)).SingleLine().Tooltip(r.Target).Bold()
						ui.Text(c, statusText(r.Status)).FontSize(12).TextColor(a.rowColor(r)).Tooltip(r.Message)
					})
				} else {
					ui.Text(c, statusText(r.Status)).FontSize(12).TextColor(a.rowColor(r)).Tooltip(r.Message)
				}
				a.removeRow(c, page, ready, r)
			})
			if page == Extract || ready {
				recessed(ui.Progress(c, r.Progress), 4).FillWidth().Height(6)
			}
		}
		if (page == Preprocess || (page == Compress && !ready)) && r.Detection.Conflict() && !r.Resolved && !r.Edited {
			ui.Row(c).FillWidth().Wrap().Gap(8).Children(func() {
				ui.Text(c, "标签冲突").FontSize(12).TextColor(a.theme.Warning)
				action(c, "用名称").Label("用名称标签").Disabled(locked).OnClick(func() { a.editTag(page, r, r.Detection.NameTag) })
				action(c, "用目录").Label("用目录标签").Disabled(locked).OnClick(func() { a.editTag(page, r, r.Detection.MarkerTag) })
			})
		}
		if r.Status == core.Failed || r.Status == core.Invalid {
			ui.Text(c, r.Message).FontSize(12).TextColor(a.rowColor(r)).Wrap().FillWidth()
		}
	})
}

const (
	preprocessNumberWidth float32 = 76
	preprocessSizeWidth   float32 = 96
	preprocessTagWidth    float32 = 124
	preprocessStatusWidth float32 = 64
	preprocessRemoveWidth float32 = 32
)

func (a *App) preprocessColumns(c *ui.Context) {
	ui.Row(c).FillWidth().Padding(0, 14).Gap(8).Children(func() {
		smallLabel(c, "当前名称").Grow(1).MinWidth(0)
		smallLabel(c, "目标名称").Grow(1).MinWidth(0)
		smallLabel(c, "编号").Width(preprocessNumberWidth)
		smallLabel(c, "大小（点击复制）").Width(preprocessSizeWidth)
		smallLabel(c, "标签").Width(preprocessTagWidth)
		smallLabel(c, "状态").Width(preprocessStatusWidth)
		ui.Column(c).Width(preprocessRemoveWidth)
	})
}
func (a *App) preprocessRow(c *ui.Context, r *Row) {
	p := a.Pages[Preprocess]
	ui.Row(c).FillWidth().Gap(8).AlignItems(ui.Center).Children(func() {
		ui.Text(c, filepath.Base(r.Path)).SingleLine().Tooltip(r.Path).Grow(1).MinWidth(0)
		ui.Text(c, filepath.Base(r.Target)).SingleLine().Tooltip(r.Target).Grow(1).MinWidth(0)
		label := "保留原名"
		if p.Sequence {
			label = "顺序编号"
		}
		action(c, label).Width(preprocessNumberWidth).Padding(6, 8).Label("切换顺序编号").Tooltip("对本页队列启用或关闭顺序编号").Disabled(a.busy(Preprocess)).OnClick(func() { p.Sequence = !p.Sequence; a.scan(Preprocess) })
		quietAction(c, r.Size).Width(preprocessSizeWidth).Label("复制大小 " + filepath.Base(r.Path)).OnClick(func() { c.WriteClipboard(r.Size) })
		input(c.Key("tag"), "编辑标签 "+filepath.Base(r.Path), &r.Tag, a.busy(Preprocess), func() { a.editTag(Preprocess, r, r.Tag) }).Width(preprocessTagWidth)
		ui.Text(c, statusText(r.Status)).FontSize(12).TextColor(a.rowColor(r)).Tooltip(r.Message).Width(preprocessStatusWidth)
		a.removeRow(c, Preprocess, false, r)
	})
}
func (a *App) sevenZipInvalid(page int) bool {
	path := a.Settings.Compression.SevenZip
	if page == Extract {
		path = a.Settings.Extraction.SevenZip
	}
	return sevenzip.ValidateExecutableName(path) != nil || a.Pages[page].ExecutableError != ""
}

func (a *App) settingsView(c *ui.Context) {
	page, p := a.Active, a.Pages[a.Active]
	locked := a.busy(page)
	titles := []string{"压缩配置", "加入标签", "解压配置", "提取标签规则"}
	card(c.Key("settings")).FillWidth().Shrink(0).Padding(16).Gap(12).Children(func() {
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			if page == Compress {
				smallLabel(c, "配置").TextColor(softAccentText).Width(30)
			}
			ui.Column(c).Grow(1).MinWidth(0).Gap(4).Children(func() {
				ui.Text(c, titles[page]).FontSize(16).Bold()
				if page == Compress {
					o := a.Settings.Compression
					encrypted := ""
					if o.HideName {
						encrypted = " · 文件名加密"
					}
					smallLabel(c, strings.TrimPrefix(o.Level, "5-")+"压缩 · "+o.Extension+" 后缀 · "+o.Dictionary+" 字典 · "+o.Threads+"线程"+encrypted).TextColor(a.theme.TextMuted).SingleLine()
				}
			})
			if page == Preprocess {
				action(c, "选择文件夹").Disabled(locked).OnClick(a.choose)
			}
			if page == Extract || page == Rename {
				action(c, "保存设置").Disabled(locked).OnClick(a.save)
			}
			label := "展开"
			if p.SettingsOpen {
				label = "收起"
			}
			action(c.Key("settings-toggle"), label).Width(70).Label(label + "配置").OnClick(func() { p.SettingsOpen = !p.SettingsOpen })
		})
		if !p.SettingsOpen {
			return
		}
		if page == Compress {
			_, h := c.Size()
			ui.Scroll(c.Key("config-scroll")).FillWidth().Height(min(260, max(140, h-540))).Children(func() { a.compressionSettings(c) })
		} else {
			a.simpleSettings(c, page)
		}
	})
}
func (a *App) inlineField(c *ui.Context, label string, value *string, width float32, changed func()) {
	ui.Row(c.Key(label)).Gap(8).AlignItems(ui.Center).Children(func() {
		smallLabel(c, label).TextColor(a.theme.TextMuted)
		input(c.Key("input"), label, value, a.busy(a.Active), changed).Width(width)
	})
}
func (a *App) field(c *ui.Context, label string, value *string, locked bool, changed func()) {
	ui.Column(c.Key(label)).FillWidth().Gap(8).Children(func() {
		smallLabel(c, label).TextColor(a.theme.TextMuted)
		input(c.Key("input"), label, value, locked, changed).FillWidth()
	})
}
func (a *App) selectField(c *ui.Context, label string, value *string, options []string, locked bool) {
	ui.Column(c.Key(label)).Grow(1).MinWidth(0).Gap(8).Children(func() {
		smallLabel(c, label).TextColor(a.theme.TextMuted)
		e := recessed(ui.Select(c.Key("select"), value, options).Label(label).Height(36).FillWidth().Disabled(locked), 10).BorderWidth(0).FocusRingOffset(2)
		e.FocusRing(e.Focused())
	})
}
func (a *App) passwordField(c *ui.Context, label string, value *string) {
	ui.Row(c.Key(label)).FillWidth().Gap(8).AlignItems(ui.Center).Children(func() {
		e := input(c.Key("password"), label, value, a.busy(a.Active), nil).Grow(1).MinWidth(0)
		if !a.ShowPassword {
			e.Password()
		}
		text := "显示"
		if a.ShowPassword {
			text = "隐藏"
		}
		action(c, text).Width(60).Label(text + "密码").OnClick(func() { a.ShowPassword = !a.ShowPassword })
	})
}
func (a *App) compressionSettings(c *ui.Context) {
	o, p := &a.Settings.Compression, a.Pages[Compress]
	locked := a.busy(Compress)
	refresh := func() { a.scan(Compress) }
	ui.Column(c).FillWidth().Padding(4).Gap(16).Children(func() {
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			smallLabel(c, "7-Zip 路径").TextColor(a.theme.TextMuted)
			input(c.Key("7zip"), "7-Zip 路径", &o.SevenZip, locked, func() { a.checkExecutable(Compress) }).Grow(1).MinWidth(80)
			action(c, "浏览").Width(62).Disabled(locked).OnClick(func() { a.choosePath(&o.SevenZip, false) })
		})
		ui.Row(c).FillWidth().Wrap().Gap(12).AlignItems(ui.Center).Children(func() {
			a.inlineField(c, "前缀", &o.Prefix, 110, refresh)
			a.inlineField(c, "后缀", &o.Extension, 64, nil)
			a.inlineField(c, "标签前缀", &o.TagPrefix, 120, refresh)
			action(c, "保存设置").Disabled(locked).OnClick(a.save)
		})
		ui.Row(c).FillWidth().Wrap().Gap(16).AlignItems(ui.Center).Children(func() {
			ui.Checkbox(c, &p.Sequence, "顺序编号").Disabled(locked).OnChange(refresh)
			ui.Checkbox(c, &p.Unwrap, "整理单层嵌套目录").Disabled(locked)
		})
		ui.Row(c).FillWidth().Gap(16).Children(func() {
			ui.Column(c).Grow(1).MinWidth(0).Gap(8).Children(func() { smallLabel(c, "压缩密码"); a.passwordField(c, "压缩密码", &o.Password) })
			ui.Column(c).Grow(1).MinWidth(0).Gap(12).Children(func() { smallLabel(c, "文件名"); ui.Checkbox(c, &o.HideName, "加密文件名").Disabled(locked) })
			a.selectField(c, "压缩等级", &o.Level, []string{"0-仅存储", "1-极快", "3-快速", "5-标准", "7-最大", "9-极限"}, locked)
			a.selectField(c, "字典大小", &o.Dictionary, []string{"64 KB", "256 KB", "1 MB", "4 MB", "16 MB", "64 MB", "128 MB", "256 MB", "512 MB", "1024 MB", "2048 MB"}, locked)
		})
		ui.Row(c).FillWidth().Gap(16).Children(func() {
			a.selectField(c, "单词大小", &o.Word, []string{"8", "12", "16", "24", "32", "48", "64", "96", "128", "192", "256", "273"}, locked)
			a.selectField(c, "固实块", &o.Solid, []string{"非固实", "64 MB", "256 MB", "1 GB", "4 GB", "16 GB", "64 GB", "固实"}, locked)
			threads := []string{"自动"}
			for i := 1; i <= runtime.NumCPU(); i++ {
				threads = append(threads, strconv.Itoa(i))
			}
			a.selectField(c, "线程数", &o.Threads, threads, locked)
			ui.Column(c).Grow(1)
		})
	})
}
func (a *App) simpleSettings(c *ui.Context, page int) {
	locked := a.busy(page)
	refresh := func() { a.scan(page) }
	if page == Preprocess {
		p, o := a.Pages[page], &a.Settings.Preprocessing
		ui.Row(c).FillWidth().Wrap().Gap(12).AlignItems(ui.Center).Children(func() {
			a.inlineField(c, "起始编号", &p.StartNumber, 78, refresh)
			action(c, "提取最小编号").Disabled(locked).OnClick(func() { a.minimumNumber(page) })
			a.inlineField(c, "文件名前缀", &o.Prefix, 120, refresh)
			a.inlineField(c, "标签前缀", &o.TagPrefix, 100, refresh)
			action(c, "保存设置").Disabled(locked).OnClick(a.save)
		})
		return
	}
	if page == Rename {
		o := &a.Settings.Renaming
		ui.Row(c).FillWidth().Gap(16).AlignItems(ui.Center).Children(func() {
			a.inlineField(c, "标签前缀", &o.TagPrefix, 150, refresh)
			smallLabel(c, "保护检测词").TextColor(a.theme.TextMuted)
			input(c.Key("terms"), "保护检测词", &o.BlockTerms, locked, refresh).Grow(1).MinWidth(0)
		})
		return
	}
	o := &a.Settings.Extraction
	ui.Column(c).FillWidth().Gap(12).Children(func() {
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			smallLabel(c, "7-Zip 路径").Width(84).TextColor(a.theme.TextMuted)
			input(c.Key("7zip"), "7-Zip 路径", &o.SevenZip, locked, func() { a.checkExecutable(page) }).Grow(1).MinWidth(0)
			action(c, "浏览").Width(72).Disabled(locked).OnClick(func() { a.choosePath(&o.SevenZip, false) })
		})
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			smallLabel(c, "解压密码").Width(84).TextColor(a.theme.TextMuted)
			ui.Column(c).Grow(1).MinWidth(100).Children(func() { a.passwordField(c, "解压密码", &o.Password) })
			a.inlineField(c, "标签前缀", &o.TagPrefix, 110, refresh)
			a.inlineField(c, "保护检测词", &o.BlockTerms, 160, refresh)
		})
		ui.Row(c).FillWidth().Gap(12).AlignItems(ui.Center).Children(func() {
			smallLabel(c, "统一输出目录").Width(84).TextColor(a.theme.TextMuted)
			input(c.Key("output"), "统一输出目录", &o.OutputDir, locked, refresh).Placeholder("留空表示解压到每个压缩包所在目录").Grow(1).MinWidth(0)
			action(c, "选择目录").Width(80).Disabled(locked).OnClick(func() { a.choosePath(&o.OutputDir, true) })
		})
	})
}
func (a *App) footer(c *ui.Context) {
	page := a.Active
	p := a.Pages[page]
	card(c.Key("dock")).FillWidth().Shrink(0).Height(76).Padding(16, 20).Children(func() {
		ui.Row(c).Fill().Gap(12).AlignItems(ui.Center).Children(func() {
			ui.Column(c).Grow(1).MinWidth(0).Gap(8).Children(func() {
				ui.Row(c).FillWidth().Gap(10).Children(func() {
					status := "队列总进度"
					if page == Preprocess {
						status = "等待开始"
					}
					if page == Rename {
						status = "等待添加文件夹"
					}
					if a.Status != "" && a.Status != "就绪" {
						status = a.Status
					}
					ui.Text(c, status).FontSize(12).SingleLine().Tooltip(status).Grow(1).MinWidth(0)
					ui.Text(c, fmt.Sprintf("%.0f%%", a.Progress*100)).FontSize(13).Bold().TextColor(softAccentText)
				})
				recessed(ui.Progress(c, a.Progress).FillWidth().Height(10), 5)
			})
			if page == Compress || (a.Job != nil && a.JobPage == Compress && a.Pages[Compress].ReadyView) {
				label := "暂停全部"
				if a.Paused {
					label = "继续"
				}
				action(c, label).Width(96).Disabled(a.Job == nil || a.JobPage != Compress || !a.Pages[Compress].ReadyView || a.Closing).OnClick(a.pause)
			}
			if page != Rename || a.Job != nil {
				label := "取消任务"
				if page == Preprocess {
					label = "取消"
				}
				action(c, label).Width(96).TextColor(a.theme.Danger).Disabled(a.Job == nil || a.Closing).OnClick(a.cancel)
			}
			label := []string{"开始压缩", "加入标签", "开始解压", "提取标签"}[page]
			rows := p.Rows
			if page == Compress {
				rows = p.Ready
			}
			run := a.start
			if page == Compress {
				run = a.compressionAction(true, a.start)
			}
			disabled := a.Job != nil || p.Scanning || len(rows) == 0 || a.errorTextFor(page, page == Compress) != ""
			primaryAction(c, label, disabled).Label("执行：" + label).Width(152).Height(40).OnClick(run)
		})
	})
}
