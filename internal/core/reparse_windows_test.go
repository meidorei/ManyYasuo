package core

import (
	"context"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestJunctionProtection(t *testing.T) {
	root := t.TempDir()
	outside := folder(t, filepath.Join(root, "outside"))
	file(t, filepath.Join(outside, "safe.txt"), "safe")
	selected := folder(t, filepath.Join(root, "selected"))
	junction := filepath.Join(selected, "wrapper")
	if out, err := exec.Command("cmd", "/c", "mklink", "/J", junction, outside).CombinedOutput(); err != nil {
		t.Fatalf("junction creation required for safety verification: %v %s", err, out)
	}
	if !IsReparse(junction) {
		t.Fatal("junction unrecognized")
	}
	size, err := FolderSize(context.Background(), selected)
	if err != nil || size != 0 {
		t.Fatal(size, err)
	}
	if n, err := Unwrap(selected, ""); err != nil || n != 0 {
		t.Fatal(n, err)
	}
	if AnalyzeRename(junction, Rules{"AAA_", ""}, nil).Status != Invalid {
		t.Fatal("junction can be renamed")
	}
	mustExist(t, filepath.Join(outside, "safe.txt"))
}
