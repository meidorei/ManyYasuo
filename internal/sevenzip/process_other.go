//go:build !windows

package sevenzip

import (
	"fmt"
	"os"
	"os/exec"
)

func configureProcess(cmd *exec.Cmd)                {}
func pauseProcess(p *os.Process, paused bool) error { return fmt.Errorf("仅支持 Windows") }
