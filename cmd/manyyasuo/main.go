package main

import (
	"log"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	"manyyasuo/assets"
	"manyyasuo/internal/config"
	"manyyasuo/internal/workbench"
)

var production = "0"

func main() {
	mygo.Theme.SetSource(mygo.ThemeLight)
	store := &config.Store{Path: config.DefaultPath(production == "1")}
	app := workbench.New(store)
	mygo.App.WhenReady(func() {
		window := mygo.NewWindow(mygo.WindowOptions{Title: "批量压缩 · 文件工作台", Width: 1360, Height: 820, MinWidth: 1080, MinHeight: 680, Content: ui.View(app.View)})
		_ = window.SetIcon(assets.Icon)
		app.Attach(window)
	})
	if err := mygo.App.Run(); err != nil {
		log.Fatal(err)
	}
}
