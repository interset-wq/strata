package crawl

import "testing"

// TestParseAuthorBox pins the PC author-box parse (docs/author-
// profile-on-demand §2.2). Minimal synthetic markup carrying the
// demonstrated class names (the page's real spelling is "autor-name").
func TestParseAuthorBox(t *testing.T) {
	html := `<html><body>
<div class="author-info">
  <div class="author-box">
    <div class="author-mask"><img src="//rss.sfacg.com/web/account/images//avatars/upload/QQ/1604/x.jpg" width="80"></div>
    <div class="autor-name">无聊看看天</div>
    <div class="author-desc">新人作者，请多包涵</div>
  </div>
</div>
</body></html>`
	box := ParseAuthorBox(html)
	if box == nil {
		t.Fatal("nil box for alive page")
	}
	if box.Name != "无聊看看天" {
		t.Fatalf("name = %q", box.Name)
	}
	if box.Intro != "新人作者，请多包涵" {
		t.Fatalf("intro = %q", box.Intro)
	}
	if box.Avatar != "https://rss.sfacg.com/web/account/images//avatars/upload/QQ/1604/x.jpg" {
		t.Fatalf("avatar = %q", box.Avatar)
	}
}

func TestParseAuthorBoxDead(t *testing.T) {
	// Dead PC pages return HTTP 200 with the negative copy (docs/05 §3,
	// docs/author-profile-on-demand §2.2) — status codes carry no
	// information, the text is the verdict.
	html := "<html><body><div>小说不存在</div></body></html>"
	if box := ParseAuthorBox(html); box != nil {
		t.Fatalf("dead page must return nil, got %+v", box)
	}
}

func TestParseAuthorBoxEmptyIntro(t *testing.T) {
	// An alive page whose author wrote no intro: intro "" is a normal
	// value — never fabricate text, never substitute the book summary
	// (§2.2).
	html := `<html><body><div class="author-box">
  <div class="autor-name">某作者</div>
  <div class="author-desc"></div>
</div></body></html>`
	box := ParseAuthorBox(html)
	if box == nil {
		t.Fatal("nil box")
	}
	if box.Intro != "" {
		t.Fatalf("intro = %q, want empty", box.Intro)
	}
	if box.Name != "某作者" {
		t.Fatalf("name = %q", box.Name)
	}
	if box.Avatar != "" {
		t.Fatalf("avatar = %q, want empty", box.Avatar)
	}
}
