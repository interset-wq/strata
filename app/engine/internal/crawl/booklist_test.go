package crawl

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// TestFetchBooklistTimeout: a stalled upstream must not pin the limiter
// worker — the per-probe timeout aborts the request (2026-11-23 device
// report: the shared client's 30s timeout per serial probe let the booklist
// window spin for minutes and froze every other foreground request behind
// the stuck job). booklistAPI and booklistTimeout are vars precisely so
// this test can point the production path at a stub.
func TestFetchBooklistTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,
		r *http.Request) {
		time.Sleep(500 * time.Millisecond)
	}))
	defer srv.Close()

	oldAPI, oldTO := booklistAPI, booklistTimeout
	booklistAPI = srv.URL
	booklistTimeout = 100 * time.Millisecond
	defer func() { booklistAPI, booklistTimeout = oldAPI, oldTO }()

	l := NewLimiter(time.Millisecond)
	defer l.Stop()

	start := time.Now()
	if _, err := FetchBooklist(context.Background(), http.DefaultClient,
		l, 1, "item", true); err == nil {
		t.Fatal("expected a timeout error from the stalled upstream")
	}
	if elapsed := time.Since(start); elapsed > 400*time.Millisecond {
		t.Fatalf("probe took %v, booklistTimeout should bound it near 100ms",
			elapsed)
	}
	// the worker must be free again — the next job runs promptly.
	freed := make(chan struct{})
	if err := l.TrySubmit(true, func() { close(freed) }); err != nil {
		t.Fatal(err)
	}
	select {
	case <-freed:
	case <-time.After(2 * time.Second):
		t.Fatal("limiter worker still pinned after the timeout")
	}
}
