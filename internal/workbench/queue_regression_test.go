package workbench

import (
	"os"
	"path/filepath"
	"testing"

	"manyyasuo/internal/core"
)

func TestCompletedExtractionSurvivesRescan(t *testing.T) {
	for _, trigger := range []string{"add", "remove", "settings"} {
		t.Run(trigger, func(t *testing.T) {
			a, q := testApp(t)
			a.Active = Extract
			root := t.TempDir()
			paths := []string{filepath.Join(root, "first.7z"), filepath.Join(root, "second.7z"), filepath.Join(root, "third.7z")}
			for _, path := range paths {
				if err := os.WriteFile(path, nil, 0600); err != nil {
					t.Fatal(err)
				}
			}
			a.addValidated(Extract, paths[:2])
			p := a.Pages[Extract]
			done, retry := p.Rows[0], p.Rows[1]
			done.Status, done.Progress = core.Done, 1
			done.Target, done.Message = filepath.Join(root, "actual-output"), "已按标签改名"
			retry.Status = core.Failed
			want := *done
			switch trigger {
			case "add":
				a.AddPaths(paths[2:])
				pump(t, a, q, func() bool { return len(p.Rows) == 3 && !p.Scanning })
			case "remove":
				a.addValidated(Extract, paths[2:])
				a.remove(Extract, p.Rows[2].ID)
				pump(t, a, q, func() bool { return !p.Scanning })
			case "settings":
				a.Settings.Extraction.OutputDir = filepath.Join(root, "new-output")
				a.Settings.Extraction.TagPrefix = "BBB_"
				a.scan(Extract)
				pump(t, a, q, func() bool { return !p.Scanning })
			}
			if *done != want {
				t.Fatalf("completed result changed after %s: got %+v, want %+v", trigger, *done, want)
			}
			if retry.Status != core.Ready {
				t.Fatalf("failed archive is no longer retryable: %+v", retry)
			}
			if trigger == "settings" && retry.Target != a.Settings.Extraction.OutputDir {
				t.Fatalf("unfinished archive did not pick up new output: %+v", retry)
			}
			// A missing executable lets us test scheduling without launching 7-Zip.
			// Its asynchronous validation failure must affect only unfinished rows.
			a.Settings.Extraction.SevenZip = filepath.Join(root, "missing", "7z.exe")
			a.start()
			if a.Job == nil {
				t.Fatal("unfinished archives were not scheduled:", p.Error)
			}
			pump(t, a, q, func() bool { return a.Job == nil })
			if *done != want || a.FailedCount != len(p.Rows)-1 || retry.Status != core.Failed {
				t.Fatalf("completed archive was rescheduled: done=%+v failed=%d retry=%+v", *done, a.FailedCount, retry)
			}
		})
	}
}

func TestCompressionImportErrorDoesNotBlockReadyQueue(t *testing.T) {
	for _, invalid := range []string{"occupied-target", "invalid-number"} {
		t.Run(invalid, func(t *testing.T) {
			a, q := testApp(t)
			root := t.TempDir()
			ready := filepath.Join(root, "HGLIST-0001 标签")
			source := filepath.Join(root, "HGLIST-0002 标签")
			for _, path := range []string{ready, source, filepath.Join(root, "HGLIST-0002")} {
				if err := os.Mkdir(path, 0755); err != nil {
					t.Fatal(err)
				}
			}
			a.addValidated(Compress, []string{ready})
			a.scan(Compress)
			pump(t, a, q, func() bool { return !a.Pages[Compress].Scanning })
			a.start()
			pump(t, a, q, func() bool { return a.Job == nil })
			p := a.Pages[Compress]
			if len(p.Ready) != 1 || len(p.Rows) != 0 {
				t.Fatal("initial folder was not prepared")
			}
			if invalid == "invalid-number" {
				p.Sequence, p.StartNumber = true, "bad"
			}
			a.AddPaths([]string{source})
			pump(t, a, q, func() bool { return len(p.Rows) == 1 && !p.Scanning })
			importError := a.errorTextFor(Compress, false)
			if importError == "" {
				t.Fatal("invalid import was not blocked")
			}
			a.compressionAction(false, a.start)()
			if a.Job != nil {
				t.Fatal("invalid import started a task")
			}
			a.Settings.Compression.SevenZip = filepath.Join(root, "missing", "7z.exe")
			if err := a.errorTextFor(Compress, true); err != "" {
				t.Fatal("ready queue blocked by import error:", err)
			}
			a.compressionAction(true, a.start)()
			if a.Job == nil {
				t.Fatal("ready queue did not start")
			}
			pump(t, a, q, func() bool { return a.Job == nil })
			if a.FailedCount != 1 || p.Ready[0].Status != core.Failed {
				t.Fatal("ready queue was not processed")
			}
			if got := a.errorTextFor(Compress, false); got != importError {
				t.Fatalf("running ready queue erased import error: got %q, want %q", got, importError)
			}
			a.compressionAction(true, func() { a.clear(Compress) })()
			if got := a.errorTextFor(Compress, false); got != importError {
				t.Fatal("clearing ready queue erased import error:", got)
			}
		})
	}
}

func TestCompressionValidationDoesNotBlockImportQueue(t *testing.T) {
	a, q := testApp(t)
	root := t.TempDir()
	source := filepath.Join(root, "HGLIST-0001 标签")
	if err := os.Mkdir(source, 0755); err != nil {
		t.Fatal(err)
	}
	a.addValidated(Compress, []string{source})
	a.scan(Compress)
	p := a.Pages[Compress]
	pump(t, a, q, func() bool { return !p.Scanning })
	a.Settings.Compression.SevenZip = ""
	a.compressionAction(true, a.start)()
	if a.Job != nil || a.errorTextFor(Compress, true) == "" {
		t.Fatal("invalid executable must block compression")
	}
	if err := a.errorTextFor(Compress, false); err != "" {
		t.Fatal("compression validation blocked import:", err)
	}
	a.compressionAction(false, a.start)()
	if a.Job == nil {
		t.Fatal("import did not start")
	}
	pump(t, a, q, func() bool { return a.Job == nil })
	if len(p.Ready) != 1 || len(p.Rows) != 0 {
		t.Fatal("import did not prepare folder")
	}
	// Fixing the executable must not leave a stale ready-stage validation error.
	a.Settings.Compression.SevenZip = filepath.Join(root, "missing", "7z.exe")
	if err := a.errorTextFor(Compress, true); err != "" {
		t.Fatal("stale compression validation:", err)
	}
}
