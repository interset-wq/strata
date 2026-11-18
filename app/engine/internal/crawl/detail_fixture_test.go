package crawl

import (
	"os"
	"testing"
)

// Real archived pages, one per state (docs/05 §2). Provenance and fetch time
// live in testdata/README.md; these are byte-for-byte server responses.
func TestParseDetailFixtures(t *testing.T) {
	cases := []struct {
		file string
		want DetailState
	}{
		{"testdata/alive_48704.html", DetailAlive},
		{"testdata/dead_73900.html", DetailDead},
		{"testdata/zombie_4733.html", DetailZombie},
	}
	for _, c := range cases {
		raw, err := os.ReadFile(c.file)
		if err != nil {
			t.Fatalf("%s: %v", c.file, err)
		}
		state, d := ParseDetail(string(raw))
		if state != c.want {
			t.Errorf("%s: state = %v, want %v", c.file, state, c.want)
			continue
		}
		switch c.want {
		case DetailAlive:
			if d == nil {
				t.Fatalf("%s: nil detail for alive page", c.file)
			}
			if d.Title == "" || d.Author == "" || d.Favs <= 0 || d.Words <= 0 {
				t.Errorf("%s: incomplete detail %+v", c.file, d)
			}
		case DetailDead:
			if d != nil {
				t.Errorf("%s: dead page must not produce a detail", c.file)
			}
		case DetailZombie:
			// Zombie pages still carry a book_info block but no reading
			// entrance; the parser must classify the state, not emit a detail.
			if d != nil {
				t.Errorf("%s: zombie page must not produce a detail", c.file)
			}
		}
	}
}
