package crawl

import (
	"context"
	"sync"
	"testing"
	"time"
)

func TestLimiterForegroundPriority(t *testing.T) {
	l := NewLimiter(10 * time.Millisecond)
	defer l.Stop()

	// Occupy the worker with a long foreground job, then queue background
	// and foreground jobs behind it. When the worker resumes, the queued
	// foreground jobs must run before the queued background ones.
	running := make(chan struct{})
	release := make(chan struct{})
	var order []string
	var mu sync.Mutex
	push := func(s string) {
		mu.Lock()
		order = append(order, s)
		mu.Unlock()
	}
	done := make(chan struct{})
	go func() {
		defer close(done)
		if err := l.Submit(context.Background(), true, func() {
			close(running)
			<-release
			push("long")
		}); err != nil {
			t.Errorf("long submit: %v", err)
		}
	}()
	<-running
	for i := 0; i < 2; i++ {
		if err := l.TrySubmit(false, func() { push("bg") }); err != nil {
			t.Fatalf("bg submit: %v", err)
		}
	}
	for i := 0; i < 2; i++ {
		if err := l.TrySubmit(true, func() { push("fg") }); err != nil {
			t.Fatalf("fg submit: %v", err)
		}
	}
	close(release)
	<-done

	// The queued jobs drain at the limiter's interval; wait for them.
	deadline := time.Now().Add(2 * time.Second)
	for {
		mu.Lock()
		n := len(order)
		mu.Unlock()
		if n == 5 || time.Now().After(deadline) {
			break
		}
		time.Sleep(2 * time.Millisecond)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(order) != 5 {
		t.Fatalf("order = %v", order)
	}
	if order[1] != "fg" || order[2] != "fg" || order[3] != "bg" || order[4] != "bg" {
		t.Fatalf("foreground did not drain before background: %v", order)
	}
}

func TestLimiterQueueFull(t *testing.T) {
	l := NewLimiter(50 * time.Millisecond)
	defer l.Stop()
	// Block the worker with one long job. Submit waits for the job to run,
	// so submit from a goroutine and release it after the queue is full.
	running := make(chan struct{})
	release := make(chan struct{})
	go func() {
		if err := l.Submit(context.Background(), true, func() {
			close(running)
			<-release
		}); err != nil {
			t.Errorf("long submit: %v", err)
		}
	}()
	<-running
	// Fill the foreground queue. TrySubmit returns right after enqueueing,
	// so the fill loop can reach queue-full while the worker is blocked.
	slots := 0
	for {
		err := l.TrySubmit(true, func() {})
		if err == ErrQueueFull {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		slots++
		if slots > queueCap {
			t.Fatal("queue accepted more than its cap")
		}
	}
	close(release)
}

func TestLimiterStop(t *testing.T) {
	l := NewLimiter(time.Millisecond)
	l.Stop()
	if err := l.Submit(context.Background(), true, func() {}); err != ErrStopped {
		t.Fatalf("submit after stop = %v", err)
	}
}
