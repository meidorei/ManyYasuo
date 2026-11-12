package jobs

import (
	"context"
	"fmt"
	"sync"
)

type Event struct {
	JobID, ItemID               uint64
	Kind, Status, Message, Path string
	Progress                    float64
	Index, Total                int
}
type Job struct {
	ID      uint64
	Owner   string
	Context context.Context
	cancel  context.CancelFunc
	Done    chan struct{}
}

func (j *Job) Cancel() { j.cancel() }

type Coordinator struct {
	mu     sync.Mutex
	next   uint64
	active *Job
}

func (c *Coordinator) Start(owner string) (*Job, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.active != nil {
		return nil, fmt.Errorf("%s 正在运行，请等待或取消当前任务", c.active.Owner)
	}
	c.next++
	ctx, cancel := context.WithCancel(context.Background())
	j := &Job{c.next, owner, ctx, cancel, make(chan struct{})}
	c.active = j
	return j, nil
}
func (c *Coordinator) Finish(j *Job) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.active != j {
		return
	}
	j.cancel()
	close(j.Done)
	c.active = nil
}
func (c *Coordinator) Active() *Job { c.mu.Lock(); defer c.mu.Unlock(); return c.active }
