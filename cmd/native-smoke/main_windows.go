//go:build smoke

package main

import (
	"fmt"
	"manyyasuo/internal/workbench"
	"os"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: native-smoke 7z.exe temporary-parent")
		os.Exit(2)
	}
	if err := workbench.RunNativeSmoke(os.Args[1], os.Args[2]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Native Win32/MyGo dispatch, preparation, compression, extraction, renaming, preprocessing and configuration: PASS")
}
