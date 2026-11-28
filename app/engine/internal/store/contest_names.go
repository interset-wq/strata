package store

import (
	_ "embed"
	"encoding/json"
)

// contest_names.json is authored by app/tools/contestledger/build_contest_names.py
// from analysis/anchors/contest_names.jsonl (our contest naming, 2026-11-27)
// joined to contest_ledger.json (legacy event keys). It is the engine's single
// translation table:
//
//   - raw: any spelling — new name (2025春征 / 崩坏3同人 / 点鸭星穹), legacy
//     official name (2025春季征文 / 崩坏3征文), or alias — to our event name
//     plus the archive series/lane.
//   - events: our event name -> series/lane and the legacy ledger row names
//     that carry its official numbers/dates/tagIds (primary first).
//
// No number is authored here: contest_ledger.json stays the sole source of
// official facts; this table only decides which row a new name points at.

type contestNameInfo struct {
	Event  string `json:"event"`
	Series string `json:"series"`
	Lane   string `json:"lane"`
}

type contestEventInfo struct {
	Series string   `json:"series"`
	Lane   string   `json:"lane"`
	Legacy []string `json:"legacy"`
}

type contestNameTable struct {
	Source map[string]string           `json:"source"`
	Raw    map[string]contestNameInfo  `json:"raw"`
	Events map[string]contestEventInfo `json:"events"`
	// eventRaw is built at init: our event name -> every raw spelling mapping
	// to it (new + legacy), for the SQL matcher.
	eventRaw map[string][]string
}

//go:embed contest_names.json
var contestNamesJSON []byte

var contestNames = func() *contestNameTable {
	var t contestNameTable
	if err := json.Unmarshal(contestNamesJSON, &t); err != nil {
		panic("store: contest_names.json: " + err.Error())
	}
	t.eventRaw = make(map[string][]string, len(t.Events))
	for raw, info := range t.Raw {
		t.eventRaw[info.Event] = append(t.eventRaw[info.Event], raw)
	}
	return &t
}()

// contestNameEvent resolves any spelling to our event name.
func contestNameEvent(raw string) (string, bool) {
	info, ok := contestNames.Raw[raw]
	return info.Event, ok
}

// contestNameForEvent returns the archive bucket/lane of an event name.
func contestNameForEvent(event string) (contestEventInfo, bool) {
	info, ok := contestNames.Events[event]
	return info, ok
}

// contestRawSpellings lists every raw spelling mapping to event (new and
// legacy alike), used to build the SQL matcher so a merged event still finds
// all of its books.
func contestRawSpellings(event string) []string {
	return contestNames.eventRaw[event]
}

// contestLegacyEvents lists the legacy ledger row names behind a new event;
// index 0 is the primary row supplying year/dates/official totals.
func contestLegacyEvents(event string) []string {
	if info, ok := contestNames.Events[event]; ok {
		return info.Legacy
	}
	return nil
}
