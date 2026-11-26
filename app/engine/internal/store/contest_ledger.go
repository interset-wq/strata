package store

import (
	_ "embed"
	"encoding/json"
)

// The contest ledger is the single built-in table of per-edition official
// facts: verified tagIds, the official entry-list size and winner count per
// track, and the schedule/activity-page record. It replaces the two hand-
// copied Go tables this file used to sit next to.
//
// Authored by app/tools/contestledger/build_ledger.py from
// contest-achieve (https://github.com/light-nook-labs/contest-achieve,
// AGPL-3.0, per-track counts captured 2026-11-24); our event/division labels
// are the key, so no upstream naming reaches the UI. Edit the ledger with that
// script — never by hand — and keep tagId provenance in
// docs/contest-roster-harvest.md §2 (the single tagId authority).

// LedgerTrackKind separates the two things a tagId can be: the official
// entry list of a track versus a winner list published as its own tag
// (early X征 635-649). Both are fetchable lists, but they never mix
// calibers: an award track is labelled 获奖名单 in the UI and never counts
// into roster_total (the participation scale).
const (
	LedgerKindRoster = "roster"
	LedgerKindAward  = "award"
)

// RosterGenNew is the 2023+ SPA endpoint
// /api/essay/getNovels?tagIds=&page=&size= (size <= 500, page 0-based).
const RosterGenNew = "new"

// RosterGenOld is the 2018-2022 H5 endpoint
// Common.ashx?op=getNovelsByTag&tagId=&ps=&pi= (ps <= 200, pi 0-based).
const RosterGenOld = "old"

// RosterTag is one verified (event, division) -> tagId mapping. Both endpoint
// generations page from 0, so no per-row page offset survives in the table
// (2026-11-26 probe: tag 704 page=0 serves 500 entries, page=1 serves the
// last 321, page=2 is empty while totalPage says 2).
type RosterTag struct {
	Event    string // event-level name (ContestEventName form, matches seed)
	Division string // roster division label; "" = single-track event
	Tag      int    // production tagId
	Gen      string // RosterGenNew or RosterGenOld
	Kind     string // LedgerKindRoster | LedgerKindAward
}

// ContestMeta is one edition's official schedule record. Year = launch year;
// Start/End/Result = official dates ("" when unknown → the archive page shows
// the year only, never a fabricated date); Note = later milestones as the
// user recorded them; URL = the verified official activity page (mobile form),
// "" hides the jump entry.
type ContestMeta struct {
	Year     int
	Start    string
	End      string
	Result   string
	Note     string
	Official string
}

type ledgerTrack struct {
	Kind     string `json:"kind"`
	Division string `json:"division"`
	Tag      int    `json:"tag"`
	Gen      string `json:"gen"`
	Roster   *int   `json:"roster"`
	Awards   *int   `json:"awards"`
}

type ledgerEvent struct {
	Name           string        `json:"name"`
	Tracks         []ledgerTrack `json:"tracks"`
	Year           *int          `json:"year"`
	Start          string        `json:"start"`
	End            string        `json:"end"`
	Result         string        `json:"result"`
	Note           string        `json:"note"`
	URL            string        `json:"url"`
	SeriesUpstream string        `json:"series_upstream"`
	RosterTotal    *int          `json:"roster_total"`
	AwardTotal     *int          `json:"award_total"`
}

type contestLedger struct {
	Source  map[string]string `json:"source"`
	Aliases map[string]string `json:"aliases"`
	Events  []ledgerEvent     `json:"events"`
	byName  map[string]ledgerEvent
	tracks  map[string][]RosterTag
}

//go:embed contest_ledger.json
var contestLedgerJSON []byte

// ledger is build-time data: a malformed table is a programming error caught
// by TestContestLedgerParses, not a runtime state to degrade through.
var ledger = func() *contestLedger {
	var l contestLedger
	if err := json.Unmarshal(contestLedgerJSON, &l); err != nil {
		panic("store: contest_ledger.json: " + err.Error())
	}
	l.byName = make(map[string]ledgerEvent, len(l.Events))
	l.tracks = make(map[string][]RosterTag, len(l.Events))
	for _, e := range l.Events {
		l.byName[e.Name] = e
		var tags []RosterTag
		for _, t := range e.Tracks {
			tags = append(tags, RosterTag{Event: e.Name, Division: t.Division,
				Tag: t.Tag, Gen: t.Gen, Kind: t.Kind})
		}
		l.tracks[e.Name] = tags
	}
	return &l
}()

// LedgerCanonical resolves a seed label spelling to the ledger's event name
// (the alias map is what stops one edition rendering as two archive rows).
func LedgerCanonical(name string) string {
	if c, ok := ledger.Aliases[name]; ok {
		return c
	}
	return name
}

// LedgerEventFor returns one event's official record, alias-resolved.
func LedgerEventFor(name string) (ledgerEvent, bool) {
	e, ok := ledger.byName[LedgerCanonical(name)]
	return e, ok
}

// ContestMetaFor returns the schedule record for an event-level name.
// Exported for the roster endpoint's TTL rule (ended events cache long,
// active ones 24h).
func ContestMetaFor(name string) (ContestMeta, bool) {
	e, ok := LedgerEventFor(name)
	if !ok {
		return ContestMeta{}, false
	}
	m := ContestMeta{Start: e.Start, End: e.End, Result: e.Result,
		Note: e.Note, Official: e.URL}
	if e.Year != nil {
		m.Year = *e.Year
	}
	return m, true
}

// RosterTagsFor returns the verified list tags for one event-level name in
// ledger order (the official division order for display) — roster and award
// tracks alike; the caller reads Kind to label the list. Nil when the event
// has no verified tag (degrade to the in-library view).
func RosterTagsFor(event string) []RosterTag {
	return ledger.tracks[LedgerCanonical(event)]
}

// LedgerListKind classifies the event's fetchable list: roster (participant
// entries) wins over award (winner lists); "" when the ledger has no tag.
// 一/二/三征 are award-only — their pages say 获奖名单, never 参赛清单.
func LedgerListKind(event string) string {
	for _, t := range RosterTagsFor(event) {
		if t.Kind == LedgerKindRoster {
			return LedgerKindRoster
		}
	}
	if tags := RosterTagsFor(event); len(tags) > 0 {
		return LedgerKindAward
	}
	return ""
}

// RosterTagFor resolves one (event, division) pair; single-track events use
// division "".
func RosterTagFor(event, division string) (RosterTag, bool) {
	// 全部 is LedgerDivisions' display label for the blank single-track
	// division; the UI round-trips chip labels back here, so it must resolve.
	if division == "全部" {
		division = ""
	}
	for _, t := range RosterTagsFor(event) {
		if t.Division == division {
			return t, true
		}
	}
	return RosterTag{}, false
}

// RosterDivisions lists an event's official tracks for the archive page's
// per-track rows: roster tracks carry the entry count, award tracks the
// winner count (Roster on an award row is only the tag list's length).
type RosterDivision struct {
	Name   string `json:"name"`
	Tag    int    `json:"tag"`
	Kind   string `json:"kind,omitempty"` // roster | award
	Roster *int   `json:"roster,omitempty"`
	Awards *int   `json:"awards,omitempty"`
}

// LedgerDivisions returns the per-track official counts for one event, in
// ledger order — roster tracks and award tracks alike (the archive page
// labels the section by kind). Nil when the event has no tag.
func LedgerDivisions(event string) []RosterDivision {
	e, ok := LedgerEventFor(event)
	if !ok {
		return nil
	}
	var out []RosterDivision
	for _, t := range e.Tracks {
		name := t.Division
		if name == "" {
			name = "全部"
		}
		out = append(out, RosterDivision{Name: name, Tag: t.Tag,
			Kind: t.Kind, Roster: t.Roster, Awards: t.Awards})
	}
	return out
}

// LedgerAwardTotal returns the official winner count for one event, when the
// ledger knows it. The winner lists themselves are not in the app yet
// (docs/contest-display-in-app.md §6): this number only sizes the reserved
// award block, it never renders as a participation count.
func LedgerAwardTotal(event string) *int {
	e, ok := LedgerEventFor(event)
	if !ok {
		return nil
	}
	return e.AwardTotal
}
