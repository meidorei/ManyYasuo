package sevenzip

import (
	"context"
	"crypto/rand"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"manyyasuo/internal/config"
	"manyyasuo/internal/core"
)

func TestCompressionArgsCompatibility(t *testing.T) {
	o := config.Defaults().Compression
	o.Password = "test secret"
	o.Solid = "固实"
	o.Threads = "2"
	args, path, err := CompressionArgs(`C:\测试目录\HGLIST-01`, o)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasSuffix(path, ".1") {
		t.Fatal(path)
	}
	for _, want := range []string{"-mhe=on", "-ptest secret", "-mmt=2", "-ms=on", "-md=64m"} {
		found := false
		for _, arg := range args {
			found = found || arg == want
		}
		if !found {
			t.Fatal(want, args)
		}
	}
	o.Extension = `../../bad`
	if _, _, err = CompressionArgs("source", o); err == nil {
		t.Fatal("invalid extension")
	}
}
func TestSplitProgressOutput(t *testing.T) {
	var values []float64
	b := &boundedOutput{last: -1, progress: func(v float64) { values = append(values, v) }}
	for _, s := range []string{"0% 中文", "\r1", "00", "%"} {
		_, _ = b.Write([]byte(s))
	}
	if !reflect.DeepEqual(values, []float64{0, 1}) {
		t.Fatal(values)
	}
	_, _ = b.Write([]byte(strings.Repeat("x", 20000)))
	if len(b.tail) > 4096 {
		t.Fatal("unbounded output")
	}
}
func sevenZipForTest(t *testing.T) string {
	t.Helper()
	exe := os.Getenv("MANYYASUO_7Z")
	if exe == "" {
		t.Skip("set MANYYASUO_7Z for real 7-Zip integration tests")
	}
	if err := ValidateExecutable(exe); err != nil {
		t.Fatal(err)
	}
	return exe
}
func TestRealRoundTripAndFailure(t *testing.T) {
	exe := sevenZipForTest(t)
	root := t.TempDir()
	source := filepath.Join(root, "HGLIST-0042")
	if err := os.Mkdir(source, 0755); err != nil {
		t.Fatal(err)
	}
	_, err := core.CreateMarker(source, "AAA_", "中文标签")
	if err != nil {
		t.Fatal(err)
	}
	content := []byte("中文与 spaces\n")
	if err = os.WriteFile(filepath.Join(source, "测试.txt"), content, 0600); err != nil {
		t.Fatal(err)
	}
	o := config.Defaults().Compression
	o.SevenZip = exe
	o.Password = "fixture-password"
	var r Runner
	archive, err := r.Compress(context.Background(), source, o, nil)
	if err != nil {
		t.Fatal(err)
	}
	e := config.Defaults().Extraction
	e.SevenZip = exe
	e.Password = o.Password
	e.OutputDir = filepath.Join(root, "output")
	out, err := r.Extract(context.Background(), archive.Path, e, nil)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(out.Path) != "HGLIST-0042 中文标签" {
		t.Fatal(out)
	}
	got, err := os.ReadFile(filepath.Join(out.Path, "测试.txt"))
	if err != nil || !reflect.DeepEqual(got, content) {
		t.Fatal(err)
	}
	e.Password = "wrong"
	if _, err = r.Extract(context.Background(), archive.Path, e, nil); err == nil {
		t.Fatal("wrong password accepted")
	}
	bad := filepath.Join(root, "broken.7z")
	_ = os.WriteFile(bad, []byte("broken"), 0600)
	if _, err = r.Extract(context.Background(), bad, e, nil); err == nil {
		t.Fatal("corrupt archive accepted")
	}
	blocked := filepath.Join(root, "file-not-dir")
	_ = os.WriteFile(blocked, []byte("keep"), 0600)
	e.OutputDir = blocked
	if _, err = r.Extract(context.Background(), archive.Path, e, nil); err == nil {
		t.Fatal("invalid output accepted")
	}
}
func TestPauseResumeAndCancelRealProcess(t *testing.T) {
	exe := sevenZipForTest(t)
	root := t.TempDir()
	source := filepath.Join(root, "large")
	_ = os.Mkdir(source, 0755)
	data := make([]byte, 32<<20)
	if _, err := rand.Read(data); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "data.bin"), data, 0600); err != nil {
		t.Fatal(err)
	}
	o := config.Defaults().Compression
	o.SevenZip = exe
	o.Level = "9-极限"
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var r Runner
	finished := make(chan error, 1)
	go func() { _, err := r.Compress(ctx, source, o, nil); finished <- err }()
	deadline := time.Now().Add(10 * time.Second)
	for {
		r.mu.Lock()
		running := r.cmd != nil
		r.mu.Unlock()
		if running {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("process did not start")
		}
		time.Sleep(5 * time.Millisecond)
	}
	for _, paused := range []bool{true, false, true} {
		if err := r.Pause(paused); err != nil {
			t.Fatal(err)
		}
	}
	cancel()
	select {
	case err := <-finished:
		if err != context.Canceled {
			t.Fatal(err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("paused process did not cancel")
	}
}
func TestStartFailureAndCancelledWait(t *testing.T) {
	root := t.TempDir()
	exe := filepath.Join(root, "7z.exe")
	_ = os.WriteFile(exe, []byte("not executable"), 0600)
	var r Runner
	if err := r.run(context.Background(), exe, nil, nil); err == nil {
		t.Fatal("launch should fail")
	}
	if err := r.Pause(true); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := r.run(ctx, exe, nil, nil); err != context.Canceled {
		t.Fatal(err)
	}
}
