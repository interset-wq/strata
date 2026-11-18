package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"strata/engine/internal/appshell"

	_ "modernc.org/sqlite"
)

var ErrNotFound = errors.New("not found")

type Store struct {
	DB       *sql.DB
	Manifest *appshell.Manifest
	SeedPath string
	UserPath string
}

type Book struct {
	NID        int64    `json:"nid"`
	Title      string   `json:"title"`
	Author     string   `json:"author"`
	Genre      *string  `json:"genre"`
	PriceType  *string  `json:"price_type"`
	Status     *string  `json:"status"`
	Contest    *string  `json:"contest"`
	Words      *int64   `json:"words"`
	Clicks     *int64   `json:"clicks"`
	Favs       *int64   `json:"favs"`
	Praises    *int64   `json:"praises"`
	Featured   bool     `json:"featured"`
	CoverURL   *string  `json:"cover_url"`
	UpdatedAt  *string  `json:"updated_at"`
	EstYear    int      `json:"est_year"`
	EstDate    string   `json:"est_date"`
	EstConf    string   `json:"est_conf"`
	Tags       *string  `json:"tags"`
	FavPctl    *float64 `json:"fav_pctl"`
	ClickPctl  *float64 `json:"click_pctl"`
	PraisePctl *float64 `json:"praise_pctl"`
	PR         *float64 `json:"pr"`
	PctlPR     *float64 `json:"pctl_pr"`
	IsLicensed bool     `json:"is_licensed"`
}

type Observation struct {
	ObservedAt    int64   `json:"observed_at"`
	Clicks        *int64  `json:"clicks"`
	Favs          *int64  `json:"favs"`
	Praises       *int64  `json:"praises"`
	Words         *int64  `json:"words"`
	ShortComments *int64  `json:"short_comments"`
	LongComments  *int64  `json:"long_comments"`
	Status        *string `json:"status"`
	UpdatedAt     *string `json:"updated_at"`
	Source        string  `json:"source"`
}

type BookDetail struct {
	Book  *Book        `json:"book"`
	Tags  []string     `json:"tags"`
	Local *Observation `json:"local"`
}

// Open attaches the read-only seed DB to the writable user DB. SQLite ATTACH
// is per-connection, so the pool is limited to one connection.
func Open(userPath, seedPath string, manifest *appshell.Manifest) (*Store, error) {
	dsn := appshell.FileURI(userPath,
		"_pragma=busy_timeout(5000)"+
			"&_pragma=journal_mode(WAL)"+
			"&_pragma=synchronous(NORMAL)"+
			"&_pragma=foreign_keys(1)")
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	seedURI := appshell.FileURI(seedPath, "mode=ro")
	if _, err := db.Exec("ATTACH DATABASE ? AS seed", seedURI); err != nil {
		db.Close()
		return nil, fmt.Errorf("attach seed: %w", err)
	}

	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM seed.books").Scan(&count); err != nil {
		db.Close()
		return nil, fmt.Errorf("read seed: %w", err)
	}
	if count != manifest.BookCount {
		db.Close()
		return nil, fmt.Errorf("seed book_count %d != manifest %d", count, manifest.BookCount)
	}

	return &Store{
		DB:       db,
		Manifest: manifest,
		SeedPath: seedPath,
		UserPath: userPath,
	}, nil
}

func (s *Store) Close() error {
	if s == nil || s.DB == nil {
		return nil
	}
	return s.DB.Close()
}

func (s *Store) SeedMeta(ctx context.Context) (map[string]string, error) {
	rows, err := s.DB.QueryContext(ctx, "SELECT key, value FROM seed.seed_meta")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	meta := map[string]string{}
	for rows.Next() {
		var key, value string
		if err := rows.Scan(&key, &value); err != nil {
			return nil, err
		}
		meta[key] = value
	}
	return meta, rows.Err()
}

func (s *Store) Book(ctx context.Context, nid int64) (*BookDetail, error) {
	const q = `
SELECT nid, title, author, genre, price_type, status, contest, words, clicks,
       favs, praises, featured, cover_url, updated_at, est_year, est_date,
       est_conf, tags, fav_pctl, click_pctl, praise_pctl, pr, pctl_pr, is_licensed
FROM seed.books WHERE nid = ?`

	var (
		b                                          Book
		genre, priceType, status, contest, cover   sql.NullString
		words, clicks, favs, praises, featured     sql.NullInt64
		updatedAt, tags                            sql.NullString
		favPctl, clickPctl, praisePctl, pr, pctlPR sql.NullFloat64
		isLicensed                                 sql.NullInt64
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&b.NID, &b.Title, &b.Author, &genre, &priceType, &status, &contest,
		&words, &clicks, &favs, &praises, &featured, &cover, &updatedAt,
		&b.EstYear, &b.EstDate, &b.EstConf, &tags,
		&favPctl, &clickPctl, &praisePctl, &pr, &pctlPR, &isLicensed,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	b.Genre = strPtr(genre)
	b.PriceType = strPtr(priceType)
	b.Status = strPtr(status)
	b.Contest = strPtr(contest)
	b.Words = intPtr(words)
	b.Clicks = intPtr(clicks)
	b.Favs = intPtr(favs)
	b.Praises = intPtr(praises)
	b.Featured = featured.Valid && featured.Int64 != 0
	b.CoverURL = strPtr(cover)
	b.UpdatedAt = strPtr(updatedAt)
	b.Tags = strPtr(tags)
	b.FavPctl = floatPtr(favPctl)
	b.ClickPctl = floatPtr(clickPctl)
	b.PraisePctl = floatPtr(praisePctl)
	b.PR = floatPtr(pr)
	b.PctlPR = floatPtr(pctlPR)
	b.IsLicensed = isLicensed.Valid && isLicensed.Int64 != 0

	tagList, err := s.bookTags(ctx, nid)
	if err != nil {
		return nil, err
	}
	local, err := s.latestObservation(ctx, nid)
	if err != nil {
		return nil, err
	}
	return &BookDetail{Book: &b, Tags: tagList, Local: local}, nil
}

func (s *Store) bookTags(ctx context.Context, nid int64) ([]string, error) {
	rows, err := s.DB.QueryContext(ctx,
		"SELECT tag FROM seed.book_tags WHERE nid = ? ORDER BY tag", nid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	tags := []string{}
	for rows.Next() {
		var tag string
		if err := rows.Scan(&tag); err != nil {
			return nil, err
		}
		tags = append(tags, tag)
	}
	return tags, rows.Err()
}

func (s *Store) latestObservation(ctx context.Context, nid int64) (*Observation, error) {
	const q = `
SELECT observed_at, clicks, favs, praises, words, short_comments, long_comments,
       status, updated_at, source
FROM main.observations
WHERE nid = ?
ORDER BY observed_at DESC
LIMIT 1`
	var (
		o                                           Observation
		clicks, favs, praises, words, shortC, longC sql.NullInt64
		status, updatedAt                           sql.NullString
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&o.ObservedAt, &clicks, &favs, &praises, &words, &shortC, &longC,
		&status, &updatedAt, &o.Source,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	o.Clicks = intPtr(clicks)
	o.Favs = intPtr(favs)
	o.Praises = intPtr(praises)
	o.Words = intPtr(words)
	o.ShortComments = intPtr(shortC)
	o.LongComments = intPtr(longC)
	o.Status = strPtr(status)
	o.UpdatedAt = strPtr(updatedAt)
	return &o, nil
}

type RankItem struct {
	Rank     int     `json:"rank"`
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	EstYear  int     `json:"est_year"`
	Favs     *int64  `json:"favs"`
	FavPctl  float64 `json:"fav_pctl"`
	Contest  *string `json:"contest"`
	CoverURL *string `json:"cover_url"`
	Status   *string `json:"status"`
	Words    *int64  `json:"words"`
	Clicks   *int64  `json:"clicks"`
}

func (s *Store) RankingFavs(ctx context.Context, year int, genre, status, contest string, limit int) ([]RankItem, error) {
	query := `
SELECT nid, title, author, genre, est_year, favs, fav_pctl, contest, cover_url
FROM seed.books
WHERE est_year = ? AND is_licensed = 0 AND fav_pctl IS NOT NULL`
	args := []any{year}
	if genre != "" {
		query += " AND genre = ?"
		args = append(args, genre)
	}
	if status != "" {
		query += " AND status = ?"
		args = append(args, status)
	}
	if contest != "" {
		// contest=1 means "any contest entry"; any other value matches one
		// specific contest name exactly.
		if contest == "1" {
			query += " AND contest != ''"
		} else {
			query += " AND contest = ?"
			args = append(args, contest)
		}
	}
	query += " ORDER BY fav_pctl DESC, nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item    RankItem
			gen     sql.NullString
			favs    sql.NullInt64
			pctl    float64
			contest sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &pctl, &contest, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.FavPctl = pctl
		item.Contest = strPtr(contest)
		items = append(items, item)
	}
	return items, rows.Err()
}

type DeepRankItem struct {
	Rank    int      `json:"rank"`
	NID     int64    `json:"nid"`
	Title   string   `json:"title"`
	Author  string   `json:"author"`
	Genre   *string  `json:"genre"`
	EstYear int      `json:"est_year"`
	Value   *float64 `json:"value"`
	Pctl    *float64 `json:"pctl"`
	InSeed  bool     `json:"in_seed"`
}

// RankingDeep reads the additive D2 table. The candidate pool is the full
// statistical universe at build time, not the curated seed book list. Depth is
// the actual board size (min(200, eligible books)); it is returned so the UI can
// show a honest "N of M" instead of pretending every board has 200 entries.
// in_seed marks whether the nid is in the curated books table: the UI uses it
// to route taps to the detail page only for seed books (others currently 404).
func (s *Store) RankingDeep(ctx context.Context, year int, metric string, limit int) ([]DeepRankItem, int, error) {
	const q = `
SELECT d.rank_no, d.nid, d.title, d.author, d.genre, d.est_year, d.value, d.pctl,
       COUNT(*) OVER() AS board_depth,
       CASE WHEN b.nid IS NULL THEN 0 ELSE 1 END AS in_seed
FROM seed.deep_ranks d
LEFT JOIN seed.books b ON b.nid = d.nid
WHERE d.est_year = ? AND d.metric = ?
ORDER BY d.rank_no ASC LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, q, year, metric, limit)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := make([]DeepRankItem, 0, limit)
	depth := 0
	for rows.Next() {
		var (
			item   DeepRankItem
			gen    sql.NullString
			value  sql.NullFloat64
			pctl   sql.NullFloat64
			inSeed int
		)
		if err := rows.Scan(&item.Rank, &item.NID, &item.Title, &item.Author,
			&gen, &item.EstYear, &value, &pctl, &depth, &inSeed); err != nil {
			return nil, 0, err
		}
		item.Genre = strPtr(gen)
		item.Value = floatPtr(value)
		item.Pctl = floatPtr(pctl)
		item.InSeed = inSeed != 0
		items = append(items, item)
	}
	return items, depth, rows.Err()
}

type ShortItem struct {
	Rank     int     `json:"rank"`
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	EstYear  int     `json:"est_year"`
	Favs     *int64  `json:"favs"`
	Words    *int64  `json:"words"`
	CoverURL *string `json:"cover_url"`
}

func (s *Store) RankingShort(ctx context.Context, limit int) ([]ShortItem, error) {
	const q = `
SELECT nid, title, author, genre, est_year, favs, words, cover_url
FROM seed.books
WHERE words <= 50000 AND status = '已完结' AND is_licensed = 0
ORDER BY favs DESC, nid ASC
LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, q, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]ShortItem, 0, limit)
	for rows.Next() {
		var (
			item  ShortItem
			gen   sql.NullString
			favs  sql.NullInt64
			words sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &words, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.Words = intPtr(words)
		items = append(items, item)
	}
	return items, rows.Err()
}

// boardKind maps the Classic board selector to its ordering column.
// All are platform cumulative values (docs/12 §1 novly showcase column).
func boardKindCol(kind string) (string, bool) {
	switch kind {
	case "recommend":
		return "praises DESC", true
	case "popular":
		return "clicks DESC", true
	case "favs":
		return "favs DESC", true
	case "new":
		return "est_date DESC", true
	case "finish":
		return "favs DESC", true // filtered to finished, still by favs
	case "words":
		return "words DESC", true
	}
	return "", false
}

// BoardBooks is the Classic full-catalog board (docs/12 showcase): platform
// cumulative values, no percentile math. Isolated from the recommendation
// signal whitelist — display only.
func (s *Store) BoardBooks(ctx context.Context, kind string, limit, offset int) ([]RankItem, error) {
	col, ok := boardKindCol(kind)
	if !ok {
		return nil, nil
	}
	q := `
SELECT nid, title, author, genre, est_year, status, words, clicks, favs, cover_url
FROM seed.books
WHERE is_licensed = 0`
	if kind == "finish" {
		q += " AND status = '已完结'"
	}
	q += fmt.Sprintf(" ORDER BY %s LIMIT ? OFFSET ?", col)
	args := []any{limit, offset}

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + offset + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	return items, rows.Err()
}

// Discover is the classic discovery stream: cover-bearing unlicensed books
// ordered by platform clicks (docs/12 §5: cover is a hard gate), keyset
// paginated by (clicks, nid) for stable, overlap-free infinite scrolling.
// cursor "" starts at the top; otherwise "clicks:nid" of the last item.
func (s *Store) Discover(ctx context.Context, cursor string, limit int) ([]RankItem, error) {
	q := `
SELECT nid, title, author, genre, est_year, status, words, clicks, favs, cover_url
FROM seed.books
WHERE is_licensed = 0 AND cover_url IS NOT NULL AND cover_url != ''`
	args := []any{}
	if cursor != "" {
		var clicks int64
		var nid int64
		if _, err := fmt.Sscanf(cursor, "%d:%d", &clicks, &nid); err != nil {
			return nil, err
		}
		q += " AND (clicks < ? OR (clicks = ? AND nid > ?))"
		args = append(args, clicks, clicks, nid)
	}
	q += " ORDER BY clicks DESC, nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	return items, rows.Err()
}

// WatchAdd puts a book on the author's watchlist (Phase 5 tracking).
func (s *Store) WatchAdd(ctx context.Context, nid int64, addedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO watchlist(nid, role, added_at) VALUES (?, 'self', ?)`,
		nid, addedAt)
	return err
}

// WatchRemove drops a book from the watchlist.
func (s *Store) WatchRemove(ctx context.Context, nid int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM watchlist WHERE nid = ?`, nid)
	return err
}

// WatchItem is a watchlist row joined with seed metadata.
type WatchItem struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	CoverURL *string `json:"cover_url"`
	AddedAt  int64   `json:"added_at"`
	Role     string  `json:"role"`
	Note     *string `json:"note"`
}

// WatchList joins the watchlist with seed metadata, newest first.
func (s *Store) WatchList(ctx context.Context) ([]WatchItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT w.nid, b.title, b.author, b.genre, b.cover_url,
       w.added_at, w.role, w.note
FROM watchlist w JOIN seed.books b ON b.nid = w.nid
ORDER BY w.added_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []WatchItem{}
	for rows.Next() {
		var (
			it         WatchItem
			gen, cover sql.NullString
			note       sql.NullString
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &gen,
			&cover, &it.AddedAt, &it.Role, &note); err != nil {
			return nil, err
		}
		it.Genre = strPtr(gen)
		it.CoverURL = strPtr(cover)
		it.Note = strPtr(note)
		items = append(items, it)
	}
	return items, rows.Err()
}

// WatchDue returns nids whose poll schedule is due: poll enabled and
// (never polled or past poll_interval). Ordered oldest-last-poll first.
func (s *Store) WatchDue(ctx context.Context, now int64, limit int) ([]int64, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid FROM watchlist
WHERE poll_enabled = 1 AND (last_poll_at IS NULL OR ? - last_poll_at >= poll_interval)
ORDER BY last_poll_at ASC LIMIT ?`, now, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	nids := []int64{}
	for rows.Next() {
		var nid int64
		if err := rows.Scan(&nid); err != nil {
			return nil, err
		}
		nids = append(nids, nid)
	}
	return nids, rows.Err()
}

// WatchPollDone stamps the completion time of a scheduled poll.
func (s *Store) WatchPollDone(ctx context.Context, nid, at int64) error {
	_, err := s.DB.ExecContext(ctx,
		`UPDATE watchlist SET last_poll_at = ? WHERE nid = ?`, at, nid)
	return err
}

// Search is the L1 local search over the bundled seed (title/author LIKE).
// Licensed books are included: they are searchable and detail-visible by
// design, just excluded from percentile rankings.
func (s *Store) Search(ctx context.Context, q string, limit int) ([]SearchItem, error) {
	const esc = `\\`
	pattern := "%" + strings.NewReplacer("%", esc+"%", "_", esc+"_", "\\", esc+esc).Replace(q) + "%"
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs
FROM seed.books
WHERE (title LIKE ? ESCAPE '\' OR author LIKE ? ESCAPE '\')
ORDER BY favs DESC, nid ASC
LIMIT ?`, pattern, pattern, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]SearchItem, 0, limit)
	for rows.Next() {
		var (
			item SearchItem
			gen  sql.NullString
			favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs); err != nil {
			return nil, err
		}
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		items = append(items, item)
	}
	return items, rows.Err()
}

// RankingNew is the new-work ranking: last two generations (est_year >=
// gen_max-1) ordered by same-generation percentile, per docs/03. Licensed
// books are excluded.
func (s *Store) RankingNew(ctx context.Context, limit int) ([]RankItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs, fav_pctl
FROM seed.books
WHERE est_year >= ? AND is_licensed = 0 AND fav_pctl IS NOT NULL
ORDER BY fav_pctl DESC, est_date DESC, nid ASC
LIMIT ?`, s.Manifest.GenMax-1, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item RankItem
			gen  sql.NullString
			favs sql.NullInt64
			pctl float64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &pctl); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.FavPctl = pctl
		items = append(items, item)
	}
	return items, rows.Err()
}

type SearchItem struct {
	NID     int64   `json:"nid"`
	Title   string  `json:"title"`
	Author  string  `json:"author"`
	Genre   *string `json:"genre"`
	EstYear int     `json:"est_year"`
	Favs    *int64  `json:"favs"`
}

// InsertObservation appends an alive-state observation (docs/05 §5.1: the
// only source of metric truth; (nid, observed_at) dedupes same-second
// fetches). Only seed.db stays untouched; this writes user.db.
func (s *Store) InsertObservation(ctx context.Context, nid, observedAt int64,
	clicks, favs, praises, words *int64, status, updatedAt *string) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO observations(nid, observed_at, clicks, favs, praises, words,
 status, updated_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'detail')`,
		nid, observedAt, clicks, favs, praises, words, status, updatedAt)
	return err
}

// Observations returns a nid's observation history, newest first.
func (s *Store) Observations(ctx context.Context, nid int64) ([]Observation, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT observed_at, clicks, favs, praises, words, short_comments,
       long_comments, status, updated_at
FROM observations WHERE nid = ? ORDER BY observed_at DESC`, nid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	// Non-nil empty slice: JSON must be [] not null (Dart side expects a list).
	items := []Observation{}
	for rows.Next() {
		var (
			o                     Observation
			clicks, favs, praises sql.NullInt64
			words, shortC, longC  sql.NullInt64
			status, updatedAt     sql.NullString
		)
		if err := rows.Scan(&o.ObservedAt, &clicks, &favs, &praises, &words,
			&shortC, &longC, &status, &updatedAt); err != nil {
			return nil, err
		}
		o.Clicks = intPtr(clicks)
		o.Favs = intPtr(favs)
		o.Praises = intPtr(praises)
		o.Words = intPtr(words)
		o.ShortComments = intPtr(shortC)
		o.LongComments = intPtr(longC)
		o.Status = strPtr(status)
		o.UpdatedAt = strPtr(updatedAt)
		items = append(items, o)
	}
	return items, rows.Err()
}

type ShelfItem struct {
	NID    int64   `json:"nid"`
	Title  string  `json:"title"`
	Author string  `json:"author"`
	Genre  *string `json:"genre"`
	AddAt  int64   `json:"added_at"`
}

// ShelfAdd records a book into the local shelf (user.db only).
func (s *Store) ShelfAdd(ctx context.Context, nid int64, addedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO shelf(nid, added_at) VALUES (?, ?)`, nid, addedAt)
	return err
}

// ShelfRemove drops a book from the shelf.
func (s *Store) ShelfRemove(ctx context.Context, nid int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM shelf WHERE nid = ?`, nid)
	return err
}

// ShelfList joins the shelf with seed titles.
func (s *Store) ShelfList(ctx context.Context) ([]ShelfItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT s.nid, b.title, b.author, b.genre, s.added_at
FROM shelf s JOIN seed.books b ON b.nid = s.nid
ORDER BY s.added_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ShelfItem{}
	for rows.Next() {
		var (
			it    ShelfItem
			genre sql.NullString
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &genre, &it.AddAt); err != nil {
			return nil, err
		}
		it.Genre = strPtr(genre)
		items = append(items, it)
	}
	return items, rows.Err()
}

// RetentionDays is the observation retention window (docs 02 §3.1:
// keep 180 days, delete in bulk, no VACUUM).
const RetentionDays = 180

// PruneObservations deletes observations older than the retention window
// and returns the number of rows removed. It runs at engine start and only
// ever touches user.db.
func (s *Store) PruneObservations(ctx context.Context, now time.Time) (int64, error) {
	cutoff := now.AddDate(0, 0, -RetentionDays).Unix()
	res, err := s.DB.ExecContext(ctx,
		`DELETE FROM observations WHERE observed_at < ?`, cutoff)
	if err != nil {
		return 0, err
	}
	n, _ := res.RowsAffected()
	return n, nil
}

// FeaturedBook is a carousel entry: featured=1 works chosen at seed build
// time (编辑精选).
type FeaturedBook struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	CoverURL *string `json:"cover_url"`
	Favs     *int64  `json:"favs"`
}

// FeaturedBooks returns up to limit featured books for the home carousel.
func (s *Store) FeaturedBooks(ctx context.Context, limit int) ([]FeaturedBook, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, cover_url, favs
FROM seed.books WHERE featured = 1
ORDER BY favs DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []FeaturedBook{}
	for rows.Next() {
		var (
			it    FeaturedBook
			cover sql.NullString
			favs  sql.NullInt64
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &cover, &favs); err != nil {
			return nil, err
		}
		it.CoverURL = strPtr(cover)
		it.Favs = intPtr(favs)
		items = append(items, it)
	}
	return items, rows.Err()
}

// UpsertCover stores an App API novelCover under the nid. Covers are
// book attributes (not observations) and live only in user.db.
func (s *Store) UpsertCover(ctx context.Context, nid int64, cover string, fetchedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO covers(nid, cover, source, fetched_at) VALUES (?, ?, 'app', ?)
ON CONFLICT(nid) DO UPDATE SET cover=excluded.cover,
 source=excluded.source, fetched_at=excluded.fetched_at`,
		nid, cover, fetchedAt)
	return err
}

// Cover returns the locally fetched cover path for a nid, if any.
func (s *Store) Cover(ctx context.Context, nid int64) (string, error) {
	var cover string
	err := s.DB.QueryRowContext(ctx,
		`SELECT cover FROM covers WHERE nid = ?`, nid).Scan(&cover)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return cover, nil
}

func strPtr(v sql.NullString) *string {
	if !v.Valid {
		return nil
	}
	s := v.String
	return &s
}

func intPtr(v sql.NullInt64) *int64 {
	if !v.Valid {
		return nil
	}
	n := v.Int64
	return &n
}

func floatPtr(v sql.NullFloat64) *float64 {
	if !v.Valid {
		return nil
	}
	f := v.Float64
	return &f
}
