package crawl

import (
	"os"
	"strings"
	"testing"
)

// Golden test per docs/05 §4.4: fixtures are real archived pages. The
// alive fixture lives in temp/ (gitignored); dead/zombie HTML is not yet
// archived (docs/05 §10 #1), so those cases use minimal synthetic pages
// until real fixtures land.
func TestParseDetailAlive(t *testing.T) {
	const fixture = "../../../../temp/_page_48704.html"
	raw, err := os.ReadFile(fixture)
	if err != nil {
		t.Skipf("fixture %s not available on this machine: %v", fixture, err)
	}
	state, d := ParseDetail(string(raw))
	if state != DetailAlive {
		t.Fatalf("state = %v", state)
	}
	if d == nil {
		t.Fatal("nil detail")
	}
	// Values from docs/05 §4.1 (nid=48704 sample; page drifts slightly over
	// time, so assert structure, not exact counters).
	if d.Favs <= 0 || d.Praises <= 0 || d.Words <= 0 {
		t.Fatalf("non-positive counters: %+v", d)
	}
	if d.Status != "已完结" {
		t.Fatalf("status = %q", d.Status)
	}
	if d.UpdatedAt != "2024-03-25 20:57:00" {
		t.Fatalf("updated_at = %q", d.UpdatedAt)
	}
	if d.Title != "英雄再临(英雄？我早就不当了)" {
		t.Fatalf("title = %q", d.Title)
	}
	if d.Author != "无聊看看天" {
		t.Fatalf("author = %q", d.Author)
	}
	if d.Genre != "科幻" || d.PriceType != "VIP" {
		t.Fatalf("genre/price = %q / %q", d.Genre, d.PriceType)
	}
	if d.CoverURL != "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2019/11/3d2f9821-16b5-4240-8086-1ff6928e2990.jpg" {
		t.Fatalf("cover_url = %q", d.CoverURL)
	}
	if !strings.Contains(d.Summary, "超级英雄") {
		t.Fatalf("summary = %q", d.Summary)
	}
}

func TestParseDetailDead(t *testing.T) {
	// Real dead pages carry the mobile negative copy with HTTP 200 (docs/05
	// §4.3); synthetic minimal page until a real fixture is archived.
	html := "<html><body><div>出错啦，你访问的页面不存在</div></body></html>"
	state, d := ParseDetail(html)
	if state != DetailDead {
		t.Fatalf("state = %v", state)
	}
	if d != nil {
		t.Fatal("dead page must not produce a detail")
	}
}

func TestParseDetailZombie(t *testing.T) {
	// Zombie: negative favs with a valid catalog entrance (docs/05 §4.3
	// negative_favs sample).
	html := `<html><body>
		<div class="book_Catalog"><a href="/i/1/">目录列表</a></div>
		<ul class="book_interact">
			<li><br>收藏<small> -58</small></li>
			<li><br>赞<small> 100</small></li>
		</ul>
		<div class="book_info3">xx / 1000字</div></body></html>`
	if state, d := ParseDetail(html); state != DetailZombie || d != nil {
		t.Fatalf("negative favs: state = %v, d = %+v", state, d)
	}

	// Zombie: empty catalog container (no <a> inside book_Catalog).
	html = `<html><body><div class="book_Catalog"></div>
		<ul class="book_interact">
			<li><br>收藏<small> 100</small></li>
			<li><br>赞<small> 100</small></li>
		</ul></body></html>`
	if state, _ := ParseDetail(html); state != DetailZombie {
		t.Fatalf("empty catalog: state = %v", state)
	}
}
