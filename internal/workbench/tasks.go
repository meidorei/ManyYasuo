package workbench

import (
	"fmt"

	"manyyasuo/internal/core"
	"manyyasuo/internal/jobs"
	"manyyasuo/internal/sevenzip"
)

func (a *App) start() {
	page := a.Active
	p := a.Pages[page]
	if a.Job != nil || p.Scanning {
		return
	}
	if err := a.errorText(page); err != "" {
		// Validation is already displayed by errorTextFor. Do not persist a
		// derived error that would remain after the user corrects the settings.
		return
	}
	stageError := &p.Error
	if page == Compress && p.ReadyView {
		stageError = &p.ReadyError
	}
	preparing := page == Preprocess || (page == Compress && !p.ReadyView)
	var rows []Row
	for _, r := range a.rows(page) {
		if preparing && r.Status == core.Invalid {
			*stageError = "请先处理全部名称或标签冲突"
			return
		}
		if r.Status == core.Done || r.Status == core.Protected || r.Status == core.NoTag || r.Status == core.AlreadyNamed {
			continue
		}
		rows = append(rows, *r)
	}
	if len(rows) == 0 {
		*stageError = "没有可执行的项目"
		return
	}
	settings := a.Settings
	prefix := a.tagPrefix(page)
	unwrap := p.Unwrap
	job, err := a.Coordinator.Start(titles[page])
	if err != nil {
		*stageError = err.Error()
		return
	}
	if p.cancelScan != nil {
		p.cancelScan()
	}
	p.Generation++
	a.Runner.Reset()
	a.Job = job
	a.JobPage = page
	a.Progress = 0
	a.Completed = 0
	a.FailedCount = 0
	a.CancelledCount = 0
	a.Paused = false
	a.Status = titles[page] + "开始运行"
	*stageError = ""
	rowIDs := map[uint64]bool{}
	for _, r := range rows {
		rowIDs[r.ID] = true
	}
	for _, r := range a.rows(page) {
		if rowIDs[r.ID] {
			r.Status = "pending"
			r.Message = "等待执行"
			r.Progress = 0
		}
	}
	emit := func(e jobs.Event) { e.JobID = job.ID; a.events <- e }
	go func() {
		defer func() {
			if panicValue := recover(); panicValue != nil {
				emit(jobs.Event{Kind: "error", Message: fmt.Sprintf("任务异常：%v", panicValue)})
			}
			a.Coordinator.Finish(job)
			emit(jobs.Event{Kind: "finished"})
		}()
		// Filesystem probes (including an unavailable network executable) must
		// stay off the render thread.
		if !preparing && (page == Compress || page == Extract) {
			executable := settings.Compression.SevenZip
			if page == Extract {
				executable = settings.Extraction.SevenZip
			}
			if err := sevenzip.ValidateExecutable(executable); err != nil {
				emit(jobs.Event{Kind: "error", Message: err.Error()})
				return
			}
		}
		if preparing {
			items := make([]core.PreprocessItem, len(rows))
			for i, r := range rows {
				items[i] = core.PreprocessItem{Source: r.Path, Target: r.Target, Tag: r.Tag, RemoveTag: r.Detection.MarkerTag}
				emit(jobs.Event{ItemID: r.ID, Kind: "status", Status: "running", Message: "正在整理目录"})
			}
			results := core.ExecutePreprocess(job.Context, items, core.PreprocessOptions{TagPrefix: prefix, Unwrap: unwrap})
			for i, r := range results {
				kind := "result"
				if page == Compress && r.Status == core.Done {
					kind = "prepared"
				}
				emit(jobs.Event{ItemID: rows[i].ID, Kind: kind, Status: r.Status, Message: r.Message, Path: r.Target, Index: i + 1, Total: len(rows), Progress: 1})
			}
			return
		}
		for i, r := range rows {
			if job.Context.Err() != nil {
				emit(jobs.Event{ItemID: r.ID, Kind: "result", Status: core.Cancelled, Message: "已取消", Index: i + 1, Total: len(rows)})
				continue
			}
			emit(jobs.Event{ItemID: r.ID, Kind: "status", Status: "running", Message: "正在处理"})
			progress := func(value float64) {
				emit(jobs.Event{ItemID: r.ID, Kind: "progress", Progress: value, Index: i, Total: len(rows)})
			}
			status, message, path := core.Done, "已完成", ""
			var taskErr error
			switch page {
			case Compress:
				out, err := a.Runner.Compress(job.Context, r.Path, settings.Compression, progress)
				taskErr = err
				message = out.Message
				path = out.Path
			case Extract:
				out, err := a.Runner.Extract(job.Context, r.Path, settings.Extraction, progress)
				taskErr = err
				message = out.Message
				path = out.Path
			case Rename:
				result := core.ExecuteRename(r.Path, core.Rules{TagPrefix: prefix, BlockTerms: settings.Renaming.BlockTerms})
				status, message, path = result.Status, result.Message, result.Target
			}
			if taskErr != nil {
				status = core.Failed
				if job.Context.Err() != nil {
					status = core.Cancelled
				}
				message += "；" + taskErr.Error()
			}
			emit(jobs.Event{ItemID: r.ID, Kind: "result", Status: status, Message: message, Path: path, Index: i + 1, Total: len(rows), Progress: 1})
		}
	}()
}
func (a *App) applyEvent(e jobs.Event) {
	if a.Job == nil || a.Job.ID != e.JobID {
		return
	}
	p := a.Pages[a.JobPage]
	if e.Kind == "error" {
		a.Status = e.Message
		for _, r := range a.rows(a.JobPage) {
			if r.Status == "running" || r.Status == "pending" {
				r.Status = core.Failed
				r.Message = e.Message
				a.FailedCount++
			}
		}
		return
	}
	if e.Kind == "finished" {
		a.Status = fmt.Sprintf("%s结束 · 完成 %d · 失败 %d · 取消 %d", titles[a.JobPage], a.Completed, a.FailedCount, a.CancelledCount)
		if a.JobPage == Compress && !p.ReadyView && len(p.Ready) > 0 {
			p.ReadyView = true
		}
		a.Job = nil
		a.JobPage = -1
		a.Paused = false
		if a.Closing && a.Window != nil {
			a.Window.Destroy()
		}
		return
	}
	var row *Row
	for _, r := range p.Rows {
		if r.ID == e.ItemID {
			row = r
			break
		}
	}
	if row == nil {
		for _, r := range p.Ready {
			if r.ID == e.ItemID {
				row = r
				break
			}
		}
	}
	if row == nil {
		return
	}
	if e.Kind == "progress" {
		row.Progress = e.Progress
		if e.Total > 0 {
			a.Progress = (float64(e.Index) + e.Progress) / float64(e.Total)
		}
		return
	}
	row.Status = e.Status
	row.Message = e.Message
	if e.Path != "" {
		row.Target = e.Path
	}
	row.Progress = e.Progress
	if e.Kind == "result" || e.Kind == "prepared" {
		switch e.Status {
		case core.Done:
			a.Completed++
		case core.Failed, core.Invalid:
			a.FailedCount++
		case core.Cancelled:
			a.CancelledCount++
		}
	}
	if e.Kind == "result" && (a.JobPage == Preprocess || a.JobPage == Rename || (a.JobPage == Compress && !p.ReadyView)) && e.Path != "" {
		row.Path = e.Path
	}
	if e.Kind == "prepared" {
		row.Path = e.Path
		row.Target = e.Path
		row.Status = core.Ready
		row.Progress = 0
		row.Message = "已整理 · 等待压缩"
		var remaining []*Row
		for _, r := range p.Rows {
			if r.ID != row.ID {
				remaining = append(remaining, r)
			}
		}
		p.Rows = remaining
		duplicate := false
		for _, r := range p.Ready {
			if core.PathKey(r.Path) == core.PathKey(row.Path) {
				duplicate = true
				break
			}
		}
		if !duplicate {
			p.Ready = append(p.Ready, row)
			p.ReadyError = ""
		}
		p.Selected = -1
	}
	if e.Total > 0 {
		a.Progress = float64(e.Index) / float64(e.Total)
	}
}
