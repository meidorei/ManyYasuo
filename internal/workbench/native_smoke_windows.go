//go:build smoke

package workbench

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	"manyyasuo/internal/config"
	"manyyasuo/internal/core"
)

// RunNativeSmoke exercises real Win32/MyGo dispatch and all four services.
// Its window stays hidden so the test never takes the user's keyboard focus.
// This harness is excluded from ordinary builds.
func RunNativeSmoke(sevenZip, tempParent string) error {
	root, err := os.MkdirTemp(tempParent, "native-smoke-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(root)
	outcome := make(chan error, 1)
	a := New(&config.Store{Path: filepath.Join(root, "config.json")})
	a.Settings.Compression.SevenZip = sevenZip
	a.Settings.Extraction.SevenZip = sevenZip
	mygo.App.WhenReady(func() {
		w := mygo.NewWindow(mygo.WindowOptions{Title: "ManyYasuo native smoke", Width: 1280, Height: 820, Hidden: true, Content: ui.View(a.View)})
		a.Attach(w)
		onMain := func(fn func()) { done := make(chan struct{}); w.Update(func() { fn(); close(done) }); <-done }
		wait := func(predicate func() bool) error {
			deadline := time.Now().Add(20 * time.Second)
			for {
				done := false
				onMain(func() { done = predicate() })
				if done {
					return nil
				}
				if time.Now().After(deadline) {
					return fmt.Errorf("native event-loop timeout")
				}
				time.Sleep(10 * time.Millisecond)
			}
		}
		go func() {
			run := func() error {
				source := filepath.Join(root, "HGLIST-0001 中文标签")
				if err := os.Mkdir(source, 0755); err != nil {
					return err
				}
				if err := os.WriteFile(filepath.Join(source, "payload.txt"), []byte("native-test"), 0600); err != nil {
					return err
				}
				onMain(func() { a.Active = Compress; a.AddPaths([]string{source}) })
				if err := wait(func() bool { return len(a.Pages[Compress].Rows) == 1 && !a.Pages[Compress].Scanning }); err != nil {
					return err
				}
				onMain(a.start)
				if err := wait(func() bool { return a.Job == nil }); err != nil {
					return err
				}
				var archive string
				var checkErr error
				onMain(func() {
					if len(a.Pages[Compress].Ready) != 1 {
						checkErr = fmt.Errorf("prepare failed: %s / %s", a.Status, a.Pages[Compress].Error)
						return
					}
					archive = a.Pages[Compress].Ready[0].Path + a.Settings.Compression.Extension
					a.start()
				})
				if checkErr != nil {
					return checkErr
				}
				if err := wait(func() bool { return a.Job == nil }); err != nil {
					return err
				}
				if !core.Exists(archive) {
					return fmt.Errorf("compression output missing")
				}
				onMain(func() {
					a.Active = Extract
					a.Settings.Extraction.OutputDir = filepath.Join(root, "output")
					a.AddPaths([]string{archive})
				})
				if err := wait(func() bool { return len(a.Pages[Extract].Rows) == 1 && !a.Pages[Extract].Scanning }); err != nil {
					return err
				}
				onMain(a.start)
				if err := wait(func() bool { return a.Job == nil }); err != nil {
					return err
				}
				if !core.Exists(filepath.Join(root, "output", "HGLIST-0001 中文标签", "payload.txt")) {
					return fmt.Errorf("extraction output missing")
				}
				renameSource := filepath.Join(root, "rename-source")
				if err := os.Mkdir(renameSource, 0755); err != nil {
					return err
				}
				if _, err := core.CreateMarker(renameSource, "AAA_", "新名称"); err != nil {
					return err
				}
				onMain(func() { a.Active = Rename; a.AddPaths([]string{renameSource}) })
				if err := wait(func() bool { return len(a.Pages[Rename].Rows) == 1 && !a.Pages[Rename].Scanning }); err != nil {
					return err
				}
				onMain(a.start)
				if err := wait(func() bool { return a.Job == nil }); err != nil {
					return err
				}
				if !core.Exists(filepath.Join(root, "新名称")) {
					return fmt.Errorf("rename failed")
				}
				pre := filepath.Join(root, "preprocess")
				if err := os.MkdirAll(filepath.Join(pre, "wrapper"), 0755); err != nil {
					return err
				}
				if err := os.WriteFile(filepath.Join(pre, "wrapper", "keep.txt"), []byte("keep"), 0600); err != nil {
					return err
				}
				onMain(func() {
					a.Active = Preprocess
					a.Pages[Preprocess].Sequence = true
					a.Pages[Preprocess].StartNumber = "0042"
					a.AddPaths([]string{pre})
				})
				if err := wait(func() bool { return len(a.Pages[Preprocess].Rows) == 1 && !a.Pages[Preprocess].Scanning }); err != nil {
					return err
				}
				onMain(func() { a.editTag(Preprocess, a.Pages[Preprocess].Rows[0], "整理标签") })
				if err := wait(func() bool { return !a.Pages[Preprocess].Scanning }); err != nil {
					return err
				}
				onMain(a.start)
				if err := wait(func() bool { return a.Job == nil }); err != nil {
					return err
				}
				for _, p := range []string{filepath.Join(root, "HGLIST-0042", "keep.txt"), filepath.Join(root, "HGLIST-0042", "AAA_整理标签")} {
					if !core.Exists(p) {
						return fmt.Errorf("preprocess output missing: %s", p)
					}
				}
				onMain(a.save)
				if !core.Exists(a.Store.Path) {
					return fmt.Errorf("config save failed")
				}
				return nil
			}
			result := run()
			outcome <- result
			mygo.RunOnMain(func() { w.Destroy() })
		}()
	})
	if err := mygo.App.Run(); err != nil {
		return err
	}
	return <-outcome
}
