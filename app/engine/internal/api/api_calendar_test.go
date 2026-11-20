package api

import (
	"net/http"
	"testing"
)

// Release-calendar endpoints (docs/14 P1). testseed dates:
//   1001/1002/1004 → 2010-01-01 (high), 1003 → 2011-01-05 (LOW),
//   1008/1009 → 2014-01-01 (high), 2001 → 2008-01-01 (licensed).

func TestCalendarDay(t *testing.T) {
	srv, _ := newTestServer(t)
	code, body := reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=day&anchor=2010-01-01", "")
	if code != http.StatusOK {
		t.Fatalf("day = %d", code)
	}
	cells := body["cells"].([]any)
	if len(cells) != 1 {
		t.Fatalf("day cells = %d, want 1", len(cells))
	}
	cell := cells[0].(map[string]any)
	if cell["date"] != "2010-01-01" || cell["total"].(float64) != 3 {
		t.Fatalf("cell = %+v, want 2010-01-01 total 3", cell)
	}
	items := cell["items"].([]any)
	if len(items) != 3 || items[0].(map[string]any)["nid"].(float64) != 1001 {
		t.Fatalf("items must be favs-desc: %+v", items)
	}
	if cell["universe"].(float64) != 5 {
		t.Fatalf("universe = %v, want 5", cell["universe"])
	}
}

func TestCalendarConfRule(t *testing.T) {
	srv, _ := newTestServer(t)
	// 1003 (low conf) on 2011-01-05: excluded from the day view…
	code, body := reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=day&anchor=2011-01-05", "")
	cell := body["cells"].([]any)[0].(map[string]any)
	if code != http.StatusOK || cell["total"].(float64) != 0 {
		t.Fatalf("low book leaked into day view: %+v", cell)
	}
	if cell["universe"].(float64) != 2 {
		t.Fatalf("universe must count the low-conf date regardless of conf: %+v", cell)
	}
	// …but present in the month view, which is totals-only.
	code, body = reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=month&anchor=2011-01-15", "")
	cells := body["cells"].([]any)
	if code != http.StatusOK || len(cells) != 31 {
		t.Fatalf("january cells = %d, want 31", len(cells))
	}
	jan5 := cells[4].(map[string]any)
	if jan5["total"].(float64) != 1 {
		t.Fatalf("month view must include the low book: %+v", jan5)
	}
	if jan5["universe"].(float64) != 2 {
		t.Fatalf("month cell universe = %v, want 2", jan5["universe"])
	}
	if _, hasItems := jan5["items"]; hasItems {
		t.Fatalf("month cells must carry totals only: %+v", jan5)
	}
}

func TestCalendarWeekAndLicensed(t *testing.T) {
	srv, _ := newTestServer(t)
	// 2014-01-02 is a Thursday; the week runs Mon 2013-12-30 .. Sun 2014-01-05.
	code, body := reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=week&anchor=2014-01-02", "")
	cells := body["cells"].([]any)
	if code != http.StatusOK || len(cells) != 7 {
		t.Fatalf("week cells = %d, want 7", len(cells))
	}
	if body["anchor"] != "2013-12-30" {
		t.Fatalf("week anchor = %v, want 2013-12-30", body["anchor"])
	}
	wed := cells[2].(map[string]any) // 2014-01-01: 1008 + 1009
	if wed["total"].(float64) != 2 {
		t.Fatalf("2014-01-01 total = %v, want 2", wed)
	}
	if wed["universe"].(float64) != 4 {
		t.Fatalf("2014-01-01 universe = %v, want 4", wed)
	}
	// licensed book 2001 (2008-01-01) must not appear
	code, body = reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=day&anchor=2008-01-01", "")
	cell := body["cells"].([]any)[0].(map[string]any)
	if code != http.StatusOK || cell["total"].(float64) != 0 {
		t.Fatalf("licensed book leaked into the calendar: %+v", cell)
	}
	if cell["universe"].(float64) != 7 {
		t.Fatalf("universe must include licensed releases: %+v", cell)
	}
}

func TestCalendarValidation(t *testing.T) {
	srv, _ := newTestServer(t)
	if code, _ := reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=hour&anchor=2010-01-01", ""); code != http.StatusBadRequest {
		t.Fatalf("bad granularity = %d, want 400", code)
	}
	if code, _ := reqJSON(t, "GET", srv.URL+"/strata/calendar?granularity=day&anchor=20100101", ""); code != http.StatusBadRequest {
		t.Fatalf("bad anchor = %d, want 400", code)
	}
}
