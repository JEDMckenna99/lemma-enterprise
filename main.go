package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func main() {
	fmt.Println("Building OPRF service...")

	// Create bin directory
	binDir := "bin"
	if err := os.MkdirAll(binDir, 0755); err != nil {
		fmt.Printf("Failed to create bin directory: %v\n", err)
		os.Exit(1)
	}

	// Build the OPRF service from oprfservice directory
	oprfDir := "oprfservice"
	outputPath := filepath.Join(binDir, "oprf-service")

	fmt.Printf("Building OPRF service from %s to %s\n", oprfDir, outputPath)

	cmd := exec.Command("go", "build", "-o", outputPath, "./oprfservice")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		fmt.Printf("Failed to build OPRF service: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("OPRF service built successfully!")

	// Make the binary executable
	if err := os.Chmod(outputPath, 0755); err != nil {
		fmt.Printf("Failed to make binary executable: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Build complete!")
}
