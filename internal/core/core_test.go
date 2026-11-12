package core

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func folder(t *testing.T, p string) string {
	t.Helper()
	if err := os.MkdirAll(p, 0755); err != nil {
		t.Fatal(err)
	}
	return p
}
func file(t *testing.T, p, value string) {
	t.Helper()
	if err := os.WriteFile(p, []byte(value), 0600); err != nil {
		t.Fatal(err)
	}
}
func marker(t *testing.T, p, prefix, tag string) string {
	t.Helper()
	m, err := CreateMarker(p, prefix, tag)
	if err != nil {
		t.Fatal(err)
	}
	return m
}
func mustExist(t *testing.T, p string) {
	t.Helper()
	if !Exists(p) {
		t.Fatalf("missing %s", p)
	}
}
func TestNames(t *testing.T) {
	for _, tt := range []struct{ in, want string }{{"a:b/c", "a_b_c"}, {"CON", "_CON"}, {"..", "未命名"}, {"A...", "A"}} {
		if got := SanitizeName(tt.in); got != tt.want {
			t.Errorf("%q => %q", tt.in, got)
		}
	}
	for _, tt := range []struct{ in, base, tag string }{{"HGLIST-0042 标签2026", "HGLIST-0042", "标签2026"}, {"HGLIST-0042 标签 (2)", "HGLIST-0042", "标签"}, {"plain", "", ""}, {"0001", "0001", ""}} {
		a, b := SplitNumberedTag(tt.in)
		if a != tt.base || b != tt.tag {
			t.Errorf("split %q: %q %q", tt.in, a, b)
		}
	}
	paths := []string{"item-10", "item-2", "item-1"}
	SortPaths(paths)
	if !reflect.DeepEqual(paths, []string{"item-1", "item-2", "item-10"}) {
		t.Fatal(paths)
	}
	if NaturalLess("a2", "A2") || NaturalLess("A2", "a2") {
		t.Fatal("case insensitive")
	}
	if LastNumber("foo10-bar0042") != "0042" {
		t.Fatal("last number")
	}
}
func TestSequence(t *testing.T) {
	root := t.TempDir()
	sources := []string{filepath.Join(root, "b"), filepath.Join(root, "a")}
	targets, err := SequenceTargets(sources, "HGLIST-", "0099")
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(targets[1]) != "HGLIST-0100" {
		t.Fatal(targets)
	}
	for _, v := range []string{"", "-1", "1.5", "一"} {
		if _, err := SequenceTargets(sources, "", v); err == nil {
			t.Fatal(v)
		}
	}
	if _, err := SequenceTargets(sources, "bad:", "1"); err == nil {
		t.Fatal("invalid prefix")
	}
}
func TestMarkerBreadthFirstAndIndependentPrefix(t *testing.T) {
	root := t.TempDir()
	nested := folder(t, filepath.Join(root, "nested"))
	marker(t, nested, "AAA_", "aaa")
	shallow := marker(t, root, "AAA_", "zzz")
	if got := FindMarker(root, "AAA_"); got != shallow {
		t.Fatal(got)
	}
	other := marker(t, root, "BBB_", "独立")
	if FindMarker(root, "BBB_") != other || FindMarker(root, "") != "" {
		t.Fatal("prefix")
	}
	first := marker(t, root, "AAA_", "bbb")
	if FindMarker(root, "AAA_") != first {
		t.Fatal("deterministic")
	}
}
func TestDetection(t *testing.T) {
	for _, tt := range []struct{ name, tag, origin, want string }{{"HGLIST-0042 标签2026", "", "name", "标签2026"}, {"HGLIST-0042", "目录", "marker", "目录"}, {"HGLIST-0042 同名", "同名", "marker", "同名"}, {"HGLIST-0042 名称", "目录", "conflict", ""}, {"plain", "", "none", ""}} {
		t.Run(tt.origin+tt.name, func(t *testing.T) {
			p := folder(t, filepath.Join(t.TempDir(), tt.name))
			if tt.tag != "" {
				marker(t, p, "AAA_", tt.tag)
			}
			d := DetectTag(p, "AAA_")
			if d.Origin != tt.origin || d.Tag != tt.want {
				t.Fatal(d)
			}
		})
	}
}
func TestProtectionDirectFileAllTerms(t *testing.T) {
	root := t.TempDir()
	file(t, filepath.Join(root, "路径.txt"), "")
	file(t, filepath.Join(root, "中文.txt"), "")
	child := folder(t, filepath.Join(root, "child"))
	file(t, filepath.Join(child, "路径中文.txt"), "")
	if BlockingFile(root, BlockTerms("路径, 中文")) != "" {
		t.Fatal("matched separate files or child")
	}
	file(t, filepath.Join(root, "路径中文.txt"), "")
	if BlockingFile(root, BlockTerms("路径；中文")) == "" {
		t.Fatal("missing blocker")
	}
}
func TestRenameAndMarkerRetention(t *testing.T) {
	for _, nonempty := range []bool{false, true} {
		t.Run(fmt.Sprint(nonempty), func(t *testing.T) {
			root := t.TempDir()
			source := folder(t, filepath.Join(root, "HGLIST-0001 旧标签"))
			m := marker(t, source, "AAA_", "新标签")
			if nonempty {
				file(t, filepath.Join(m, "keep.txt"), "data")
			}
			r := ExecuteRename(source, Rules{"AAA_", ""})
			if r.Status != Done || filepath.Base(r.Target) != "HGLIST-0001 新标签" {
				t.Fatal(r)
			}
			if nonempty {
				mustExist(t, filepath.Join(r.Target, "AAA_新标签", "keep.txt"))
			} else if Exists(filepath.Join(r.Target, "AAA_新标签")) {
				t.Fatal("empty marker retained")
			}
		})
	}
}
func TestRenameReservedAndAlreadyNamed(t *testing.T) {
	root := t.TempDir()
	var sources []string
	for _, n := range []string{"a", "b"} {
		p := folder(t, filepath.Join(root, n))
		marker(t, p, "AAA_", "same")
		sources = append(sources, p)
	}
	p := AnalyzeRenames(sources, Rules{"AAA_", ""})
	if filepath.Base(p[0].Target) != "same" || filepath.Base(p[1].Target) != "same (2)" {
		t.Fatal(p)
	}
	named := folder(t, filepath.Join(root, "HGLIST-1 same (2)"))
	marker(t, named, "AAA_", "same")
	if AnalyzeRename(named, Rules{"AAA_", ""}, nil).Status != AlreadyNamed {
		t.Fatal("already named")
	}
}
func TestPreprocessCycleAndIntegration(t *testing.T) {
	root := t.TempDir()
	a := folder(t, filepath.Join(root, "HGLIST-0002"))
	b := folder(t, filepath.Join(root, "HGLIST-0001"))
	file(t, filepath.Join(a, "first.txt"), "1")
	file(t, filepath.Join(b, "second.txt"), "2")
	r := ExecutePreprocess(context.Background(), []PreprocessItem{{a, b, "甲", ""}, {b, a, "乙", ""}}, PreprocessOptions{"AAA_", false})
	for _, v := range r {
		if v.Status != Done {
			t.Fatal(r)
		}
	}
	mustExist(t, filepath.Join(b, "first.txt"))
	mustExist(t, filepath.Join(a, "second.txt"))
	if AnalyzeRename(b, Rules{"AAA_", ""}, nil).Tag != "甲" {
		t.Fatal("cross-module tag")
	}
}
func TestPreprocessKeepNameStripTagAndReplaceMarker(t *testing.T) {
	for _, nonempty := range []bool{false, true} {
		t.Run(fmt.Sprint(nonempty), func(t *testing.T) {
			root := t.TempDir()
			source := folder(t, filepath.Join(root, "HGLIST-0042 旧标签"))
			m := marker(t, source, "AAA_", "旧标签")
			if nonempty {
				file(t, filepath.Join(m, "keep.txt"), "safe")
			}
			r := ExecutePreprocess(context.Background(), []PreprocessItem{{Source: source, Target: source, Tag: "新标签"}}, PreprocessOptions{"AAA_", false})[0]
			if filepath.Base(r.Target) != "HGLIST-0042" {
				t.Fatal(r)
			}
			if nonempty {
				if r.Status != Failed {
					t.Fatal(r)
				}
				mustExist(t, filepath.Join(r.Target, "AAA_旧标签", "keep.txt"))
				if Exists(filepath.Join(r.Target, "AAA_新标签")) {
					t.Fatal("created competing marker")
				}
			} else {
				if r.Status != Done {
					t.Fatal(r)
				}
				mustExist(t, filepath.Join(r.Target, "AAA_新标签"))
			}
		})
	}
}
func TestPreprocessValidationBlocksWholeBatch(t *testing.T) {
	root := t.TempDir()
	a := folder(t, filepath.Join(root, "a"))
	b := folder(t, filepath.Join(root, "b"))
	occupied := folder(t, filepath.Join(root, "occupied"))
	r := ExecutePreprocess(context.Background(), []PreprocessItem{{a, occupied, "", ""}, {b, filepath.Join(root, "new"), "", ""}}, PreprocessOptions{})
	if r[0].Status != Invalid || r[1].Status != Cancelled {
		t.Fatal(r)
	}
	mustExist(t, a)
	mustExist(t, b)
	if _, err := AnalyzePreprocess([]PreprocessItem{{a, a, "", ""}, {a, a, "", ""}}); err == nil {
		t.Fatal("duplicate")
	}
	child := folder(t, filepath.Join(a, "child"))
	if _, err := AnalyzePreprocess([]PreprocessItem{{a, a, "", ""}, {child, child, "", ""}}); err == nil {
		t.Fatal("nested sources")
	}
}
func TestRollbackEveryRename(t *testing.T) {
	for failure := 1; failure <= 4; failure++ {
		t.Run(fmt.Sprint(failure), func(t *testing.T) {
			root := t.TempDir()
			a := folder(t, filepath.Join(root, "A"))
			b := folder(t, filepath.Join(root, "B"))
			file(t, filepath.Join(a, "a.txt"), "A")
			file(t, filepath.Join(b, "b.txt"), "B")
			calls := 0
			rename := func(from, to string) error {
				calls++
				if calls == failure {
					return fmt.Errorf("injected")
				}
				return os.Rename(from, to)
			}
			r := executePreprocess(context.Background(), []PreprocessItem{{a, b, "", ""}, {b, a, "", ""}}, PreprocessOptions{}, rename)
			for _, v := range r {
				if v.Status != Failed {
					t.Fatal(r)
				}
			}
			mustExist(t, filepath.Join(a, "a.txt"))
			mustExist(t, filepath.Join(b, "b.txt"))
		})
	}
}
func TestRollbackFailureReportsLocation(t *testing.T) {
	root := t.TempDir()
	a := folder(t, filepath.Join(root, "A"))
	b := folder(t, filepath.Join(root, "B"))
	file(t, filepath.Join(a, "a.txt"), "A")
	file(t, filepath.Join(b, "b.txt"), "B")
	calls := 0
	r := executePreprocess(context.Background(), []PreprocessItem{{a, b, "", ""}, {b, a, "", ""}}, PreprocessOptions{}, func(from, to string) error {
		calls++
		if calls >= 4 {
			return fmt.Errorf("injected recovery failure")
		}
		return os.Rename(from, to)
	})
	for i, v := range r {
		if v.Status != Failed || v.Target == "" {
			t.Fatal(r)
		}
		name := "a.txt"
		if i == 1 {
			name = "b.txt"
		}
		mustExist(t, filepath.Join(v.Target, name))
	}
}
func TestCancelBeforeMutation(t *testing.T) {
	p := folder(t, filepath.Join(t.TempDir(), "keep"))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r := ExecutePreprocess(ctx, []PreprocessItem{{p, filepath.Join(filepath.Dir(p), "new"), "", ""}}, PreprocessOptions{})
	if r[0].Status != Cancelled {
		t.Fatal(r)
	}
	mustExist(t, p)
}
func TestUnwrapAndSize(t *testing.T) {
	root := t.TempDir()
	nested := folder(t, filepath.Join(root, "one", "two"))
	file(t, filepath.Join(nested, "data.txt"), "abc")
	n, err := Unwrap(root, "AAA_")
	if err != nil || n != 2 {
		t.Fatal(n, err)
	}
	size, err := FolderSize(context.Background(), root)
	if err != nil || size != 3 {
		t.Fatal(size, err)
	}
	if FormatSize(1536) != "1.5 KB" {
		t.Fatal(FormatSize(1536))
	}
	other := t.TempDir()
	m := marker(t, other, "AAA_", "保留")
	if n, err = Unwrap(other, "AAA_"); n != 0 || err != nil {
		t.Fatal(n, err)
	}
	mustExist(t, m)
}
func TestFinalizeAndPartialExtraction(t *testing.T) {
	root := t.TempDir()
	stage := folder(t, filepath.Join(root, ".stage"))
	payload := folder(t, filepath.Join(stage, "HGLIST-0007 旧名"))
	marker(t, payload, "AAA_", "联动")
	file(t, filepath.Join(payload, "a.txt"), "data")
	dest, _, err := FinalizeExtraction(stage, root, "archive.1", Rules{"AAA_", ""})
	if err != nil || filepath.Base(dest) != "HGLIST-0007 联动" {
		t.Fatal(dest, err)
	}
	mustExist(t, filepath.Join(dest, "a.txt"))
	stage = folder(t, filepath.Join(root, ".failed"))
	file(t, filepath.Join(stage, "part.txt"), "safe")
	kept := PreservePartial(stage, root, "archive")
	mustExist(t, filepath.Join(kept, "part.txt"))
	stage = folder(t, filepath.Join(root, ".empty"))
	if PreservePartial(stage, root, "archive") != "" {
		t.Fatal("empty stage retained")
	}
}
