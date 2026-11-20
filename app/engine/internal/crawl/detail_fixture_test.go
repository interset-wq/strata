package crawl

import (
	"os"
	"strings"
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
			// Author section (book_Author, docs/author-profile-on-demand
			// §2.1): avatar + display name + 作品集 links, all from the
			// same archived page — no second request.
			if d.AuthorName != "无聊看看天" {
				t.Errorf("%s: author_name = %q", c.file, d.AuthorName)
			}
			if d.AuthorAvatar == "" || !strings.Contains(d.AuthorAvatar, "avatars") {
				t.Errorf("%s: author_avatar = %q", c.file, d.AuthorAvatar)
			}
			if len(d.AuthorWorks) != 6 {
				t.Errorf("%s: author_works = %d, want 6: %+v",
					c.file, len(d.AuthorWorks), d.AuthorWorks)
			} else if d.AuthorWorks[0].NID != 48704 || d.AuthorWorks[5].NID != 52614 {
				t.Errorf("%s: author_works order = %+v", c.file, d.AuthorWorks)
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
