package jobs

import (
	"sync"
	"sync/atomic"
	"testing"
)

func TestMutualExclusionAndOwnerRelease(t *testing.T) {
	var c Coordinator
	first, err := c.Start("压缩")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.Start("解压"); err == nil {
		t.Fatal("concurrent job")
	}
	c.Finish(&Job{})
	if c.Active() != first {
		t.Fatal("wrong owner released")
	}
	first.Cancel()
	if first.Context.Err() == nil {
		t.Fatal("cancel")
	}
	c.Finish(first)
	c.Finish(first)
	if _, err = c.Start("新任务"); err != nil {
		t.Fatal(err)
	}
}
func TestConcurrentStart(t *testing.T) {
	var c Coordinator
	var count atomic.Int32
	var wg sync.WaitGroup
	for range 20 {
		wg.Go(func() {
			if _, err := c.Start("job"); err == nil {
				count.Add(1)
			}
		})
	}
	wg.Wait()
	if count.Load() != 1 {
		t.Fatal(count.Load())
	}
	c.Finish(c.Active())
}
