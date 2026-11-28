package crawl

import (
	"os"
	"testing"
)

// TestParseVipPush uses the real 2026-11-28 H5 page: 26 light-novel entries,
// protocol-relative cover, genre span plus slash-separated tags.
func TestParseVipPush(t *testing.T) {
	page, err := os.ReadFile("testdata/vippush_20261128.html")
	if err != nil {
		t.Fatal(err)
	}
	items := ParseVipPush(string(page))
	if len(items) != 26 {
		t.Fatalf("parsed %d items, want 26", len(items))
	}
	first := items[0]
	if first.Nid != 786432 {
		t.Errorf("first nid = %d, want 786432", first.Nid)
	}
	if first.Title != "反派大师兄才不会是纯爱宗圣女！" {
		t.Errorf("first title = %q", first.Title)
	}
	if first.Genre != "玄幻" {
		t.Errorf("first genre = %q, want 玄幻", first.Genre)
	}
	if len(first.Tags) != 4 || first.Tags[0] != "女性主角" {
		t.Errorf("first tags = %v", first.Tags)
	}
	if first.Cover == "" || first.Cover[:6] != "https:" {
		t.Errorf("first cover = %q, want https://", first.Cover)
	}
	// 最后一个 book block 也要命中（尾部无下一个 data-nid 节点）。
	last := items[len(items)-1]
	if last.Nid != 784359 || last.Title != "与青梅竹马同居的距离" {
		t.Errorf("last item = %+v", last)
	}
	// tab 头 <div class="item">轻小说/对话小说</div> 不应混入。
	for _, it := range items {
		if it.Nid == 0 {
			t.Fatalf("tab header leaked into parsed items: %+v", it)
		}
	}
}

func TestParseVipPushEmpty(t *testing.T) {
	if got := ParseVipPush("<html><body>no books</body></html>"); len(got) != 0 {
		t.Fatalf("empty page parsed %d items", len(got))
	}
}
