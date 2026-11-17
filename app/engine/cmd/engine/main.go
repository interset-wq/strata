package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"strata/engine/internal/engine"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "engine:", err)
		os.Exit(1)
	}
}

func run() error {
	assetsFlag := flag.String("assets", "", "directory containing manifest.json + seed.db.gz")
	dataFlag := flag.String("data-dir", "", "writable app data directory")
	flag.Parse()

	e, err := engine.StartWithFlags(*assetsFlag, *dataFlag)
	if err != nil {
		return err
	}

	fmt.Printf("STRATA_ADDR=%s\n", e.Addr())
	fmt.Printf("STRATA_SEED=%s\n", e.Manifest().SeedVersion)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	select {
	case err := <-e.Done():
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return e.Shutdown(shutdownCtx)
	}
}
