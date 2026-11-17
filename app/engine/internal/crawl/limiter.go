// Package crawl implements the shared rate limiter and the mobile-page
// detail fetcher. Rate-limit rules per docs/05 and the endpoint fact file:
// one global limiter shared by all SFACG requests, foreground
// (user-triggered) jobs drain before background jobs, and an overflowing
// queue is dropped immediately rather than piling up.
package crawl

import (
	"context"
	"errors"
	"sync"
	"time"
)

// ErrQueueFull is returned by Submit when the queue for the given priority
// is full. Callers must treat it as "dropped", not retry inline.
var ErrQueueFull = errors.New("crawl: queue full")

// ErrStopped is returned by Submit after Stop.
var ErrStopped = errors.New("crawl: limiter stopped")

// DefaultInterval is the conservative single-request spacing (the fact file
// measured 0.25s as safe for mobile pages; 1s globally stays well clear of
// the HTML-search silent throttle).
const DefaultInterval = time.Second

// queueCap bounds both queues; overflow is dropped.
const queueCap = 8

type job struct {
	fn   func()
	done chan struct{}
}

// Limiter serializes SFACG requests with foreground priority.
type Limiter struct {
	interval time.Duration
	fg, bg   chan job
	stopc    chan struct{}
	stopped  sync.Once
	stoppedM sync.Mutex
	stoppedF bool
	wg       sync.WaitGroup
}

// NewLimiter starts the drain loop. Stop waits for the loop to exit.
func NewLimiter(interval time.Duration) *Limiter {
	l := &Limiter{
		interval: interval,
		fg:       make(chan job, queueCap),
		bg:       make(chan job, queueCap),
		stopc:    make(chan struct{}),
	}
	l.wg.Add(1)
	go l.loop()
	return l
}

func (l *Limiter) loop() {
	defer l.wg.Done()
	for {
		// Foreground first: drain it entirely before touching background.
		select {
		case j := <-l.fg:
			j.run()
			if !l.wait() {
				return
			}
			continue
		default:
		}
		select {
		case j := <-l.fg:
			j.run()
		case j := <-l.bg:
			j.run()
		case <-l.stopc:
			return
		}
		if !l.wait() {
			return
		}
	}
}

// wait spaces requests by the interval; false when the limiter stops.
func (l *Limiter) wait() bool {
	t := time.NewTimer(l.interval)
	defer t.Stop()
	select {
	case <-t.C:
		return true
	case <-l.stopc:
		return false
	}
}

func (j job) run() {
	defer close(j.done)
	j.fn()
}

// Submit enqueues fn at the given priority and waits for it to run.
// Returns ErrQueueFull when the queue is full (dropped), ErrStopped after
// Stop, or the ctx error if ctx ends before the job runs. A queued job
// always runs even if ctx is cancelled afterwards.
func (l *Limiter) Submit(ctx context.Context, foreground bool, fn func()) error {
	j, err := l.enqueue(foreground, fn)
	if err != nil {
		return err
	}
	select {
	case <-j.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// TrySubmit enqueues fn without waiting for it to run.
func (l *Limiter) TrySubmit(foreground bool, fn func()) error {
	_, err := l.enqueue(foreground, fn)
	return err
}

func (l *Limiter) enqueue(foreground bool, fn func()) (job, error) {
	l.stoppedM.Lock()
	if l.stoppedF {
		l.stoppedM.Unlock()
		return job{}, ErrStopped
	}
	l.stoppedM.Unlock()

	j := job{fn: fn, done: make(chan struct{})}
	q := l.bg
	if foreground {
		q = l.fg
	}
	select {
	case q <- j:
		return j, nil
	default:
		return job{}, ErrQueueFull
	}
}

// Stop shuts the limiter down and waits for the loop to exit. Queued jobs
// already submitted may not run.
func (l *Limiter) Stop() {
	l.stoppedM.Lock()
	l.stoppedF = true
	l.stoppedM.Unlock()
	l.stopped.Do(func() { close(l.stopc) })
	l.wg.Wait()
}
