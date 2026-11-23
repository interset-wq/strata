// Runtime dating for discovered books (app/docs/18-runtime-metrics.md P2):
// a Go port of analysis/lib/eras.py — log(nid) ↔ day piecewise-linear
// interpolation over the shipped eras_anchors table (report 01; median
// interpolation error 2 days). Confidence follows the analysis tiers:
// exact for anchor nids, high/mid/low by the bracketing anchors' day gap
// for interpolated segments, always low for extrapolation.
package store

import (
	"context"
	"math"
	"sort"
	"time"
)

type eraAnchor struct {
	nid  int64
	day  float64
	lnid float64
}

// loadErasAnchors reads the shipped dating curve, ordered by nid.
func (s *Store) loadErasAnchors(ctx context.Context) ([]eraAnchor, error) {
	rows, err := s.DB.QueryContext(ctx,
		"SELECT nid, day FROM seed.eras_anchors ORDER BY nid")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []eraAnchor
	for rows.Next() {
		var a eraAnchor
		if err := rows.Scan(&a.nid, &a.day); err != nil {
			return nil, err
		}
		a.lnid = math.Log(math.Max(float64(a.nid), 1))
		out = append(out, a)
	}
	return out, rows.Err()
}

// EstimateYear dates one nid; ok=false when no anchors shipped. conf is
// exact/high/mid/low — the same tiers as the analysis calibre.
func (s *Store) EstimateYear(ctx context.Context, nid int64) (year int, conf string, ok bool, err error) {
	anchors, err := s.loadErasAnchors(ctx)
	if err != nil {
		return 0, "", false, err
	}
	if len(anchors) == 0 {
		return 0, "", false, nil
	}
	x := math.Log(math.Max(float64(nid), 1))
	i := sort.Search(len(anchors), func(i int) bool { return anchors[i].lnid >= x })

	var day float64
	if i == 0 {
		// Below the first anchor: extrapolate on the first segment's slope.
		day = anchors[0].day + (x-anchors[0].lnid)*loSlope(anchors)
	} else if i == len(anchors) {
		last := anchors[len(anchors)-1]
		day = last.day + (x-last.lnid)*hiSlope(anchors)
	} else {
		a, b := anchors[i-1], anchors[i]
		day = a.day + (x-a.lnid)*(b.day-a.day)/(b.lnid-a.lnid)
	}
	year = time.Unix(0, 0).UTC().AddDate(0, 0, int(math.Round(day))).Year()

	conf = "low"
	if i > 0 && i < len(anchors) {
		gap := math.Abs(anchors[i].day - anchors[i-1].day)
		if gap <= 90 {
			conf = "high"
		} else if gap <= 365 {
			conf = "mid"
		}
	}
	if j := sort.Search(len(anchors), func(j int) bool { return anchors[j].nid >= nid }); j < len(anchors) && anchors[j].nid == nid {
		conf = "exact"
	}
	return year, conf, true, nil
}

// loSlope/hiSlope port eras._Model._edge_slopes: the first non-degenerate
// segment from each end.
func loSlope(a []eraAnchor) float64 {
	n := len(a)
	j := n - 1
	for j > 0 && (a[j].day == a[j-1].day || a[j].lnid == a[j-1].lnid) {
		j--
	}
	return (a[j].day - a[j-1].day) / (a[j].lnid - a[j-1].lnid)
}

func hiSlope(a []eraAnchor) float64 {
	i := 0
	for i < len(a)-1 && (a[i].day == a[i+1].day || a[i].lnid == a[i+1].lnid) {
		i++
	}
	return (a[i+1].day - a[i].day) / (a[i+1].lnid - a[i].lnid)
}
