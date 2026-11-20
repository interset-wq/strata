package eras

import (
	"math"
	"sort"
	"time"
)

// anchor: one verified creation-time data point. nid is the site's
// globally auto-incrementing primary key (strictly monotonic), so the
// nid ↔ creation-date map is interpolated between anchors.
type anchor struct {
	NID int64
	Day int // days since 1970-01-01 (UTC)
}

// Result is one nid's dating verdict.
type Result struct {
	IsAnchor   bool   // the nid itself is an anchor (official addTime)
	EstDate    string // YYYY-MM-DD
	EstYear    int
	Mode       string // extrap_low | interp | extrap_high
	Confidence string // exact | high | mid | low (extrapolation → low)
}

func ln(v float64) float64 { return math.Log(math.Max(v, 1.0)) }

func isAnchor(nid int64) bool {
	i := sort.Search(len(anchors), func(i int) bool { return anchors[i].NID >= nid })
	return i < len(anchors) && anchors[i].NID == nid
}

// edgeSlopes mirrors eras.py _edge_slopes: end segments often share the
// same second-level timestamp — the extrapolation slope must skip
// same-instant points, or out-of-range nids collapse onto one day.
func edgeSlopes() (lo, hi float64) {
	n := len(anchors)
	j := n - 1
	for j > 0 && (anchors[j].Day == anchors[j-1].Day || anchors[j].NID == anchors[j-1].NID) {
		j--
	}
	lo = float64(anchors[j].Day-anchors[j-1].Day) / (ln(float64(anchors[j].NID)) - ln(float64(anchors[j-1].NID)))
	i := 0
	for i < n-1 && (anchors[i].Day == anchors[i+1].Day || anchors[i].NID == anchors[i+1].NID) {
		i++
	}
	hi = float64(anchors[i+1].Day-anchors[i].Day) / (ln(float64(anchors[i+1].NID)) - ln(float64(anchors[i].NID)))
	return lo, hi
}

// Estimate maps one nid to its creation date — a faithful port of
// analysis/lib/eras.py::estimate: piecewise-linear log(nid) ↔ day
// interpolation over the embedded 281-anchor table, edge-slope
// extrapolation at both ends, confidence tiered by the date span of the
// bracketing anchors (exact for anchor nids, low for extrapolation).
func Estimate(nid int64) Result {
	x := ln(float64(nid))
	loN := anchors[0].NID
	hiN := anchors[len(anchors)-1].NID

	mode := "interp"
	var day float64
	switch {
	case float64(nid) < float64(loN):
		slope, _ := edgeSlopes()
		day = float64(anchors[0].Day) + (x-ln(float64(loN)))*slope
		mode = "extrap_low"
	case float64(nid) > float64(hiN):
		_, slope := edgeSlopes()
		day = float64(anchors[len(anchors)-1].Day) + (x-ln(float64(hiN)))*slope
		mode = "extrap_high"
	default:
		i := sort.Search(len(anchors), func(i int) bool { return anchors[i].NID >= nid })
		if i == 0 {
			day = float64(anchors[0].Day)
		} else {
			loA, hiA := anchors[i-1], anchors[i]
			loX, hiX := ln(float64(loA.NID)), ln(float64(hiA.NID))
			day = float64(loA.Day)
			if hiX > loX {
				day += (x - loX) / (hiX - loX) * float64(hiA.Day-loA.Day)
			}
		}
	}

	// Confidence by the date span of the bracketing anchors (not the
	// nid span); extrapolated rows are overridden to low, anchor rows
	// to exact (their est_date reproduces the official addTime).
	idx := sort.Search(len(anchors), func(i int) bool { return anchors[i].NID >= nid })
	loI := idx - 1
	if loI < 0 {
		loI = 0
	}
	hiI := idx
	if hiI > len(anchors)-1 {
		hiI = len(anchors) - 1
	}
	gap := math.Abs(float64(anchors[hiI].Day - anchors[loI].Day))

	conf := "high"
	switch {
	case gap > 365:
		conf = "low"
	case gap > 90:
		conf = "mid"
	}
	if mode != "interp" {
		conf = "low"
	}
	hit := isAnchor(nid)
	if hit {
		conf = "exact"
	}

	date := time.Unix(0, 0).UTC().AddDate(0, 0, int(math.Round(day)))
	return Result{
		IsAnchor:   hit,
		EstDate:    date.Format("2006-01-02"),
		EstYear:    date.Year(),
		Mode:       mode,
		Confidence: conf,
	}
}
