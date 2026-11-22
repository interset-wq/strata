package store

import "testing"

// TestParseNIDQuery pins the nid-search boundary: 4+ all-digit queries are
// exact id lookups; 1–3 digit strings, non-digit chars and int64 overflow
// all stay on the keyword path (docs/08 §search).
func TestParseNIDQuery(t *testing.T) {
	cases := []struct {
	q  string
	n  int64
	ok bool
	}{
		{"", 0, false},
		{"7", 0, false},
		{"999", 0, false},
		{"1000", 1000, true},
		{"705464", 705464, true},
		{"12a4", 0, false},
		{"10 1", 0, false},
		{"99999999999999999999", 0, false}, // int64 overflow
	}
	for _, c := range cases {
		if n, ok := parseNIDQuery(c.q); n != c.n || ok != c.ok {
			t.Errorf("parseNIDQuery(%q) = (%d, %v), want (%d, %v)",
				c.q, n, ok, c.n, c.ok)
		}
	}
}
