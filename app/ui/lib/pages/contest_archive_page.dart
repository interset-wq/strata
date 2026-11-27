import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/format.dart';
import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 单届赛事档案（docs/contest-display-in-app.md 形态一）：本地零请求视图。
///
/// 2026-11-26 改版（用户认可）：头部改「元信息 → 赛程三点 → 规模三数 →
/// 库内覆盖率」——旧版只有一句赛程文本和一个在库数，读者分不清「这届多大」
/// 和「我们库里有多少」，覆盖率把差距本身变成信息；动作区从三个叠放的整宽
/// 按钮收成两行一事、右侧带数（在库 335 本 / 官方清单 4,797 条）。
/// 台账缺哪段就省哪个节点，日期与链接一律不编造。
class ContestArchivePage extends StatefulWidget {
  const ContestArchivePage({super.key, required this.name});

  final String name;

  @override
  State<ContestArchivePage> createState() => _ContestArchivePageState();
}

class _ContestArchivePageState extends State<ContestArchivePage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.hasClients && _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.name)),
      body: Stack(
        children: [
          _Body(name: widget.name, scroll: _scroll),
          if (_showTop)
            Positioned(
              right: 16,
              bottom: 24,
              child: BackToTop(
                onTap: () => _scroll.animateTo(
                  0,
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

const _formLabels = {
  'long': '长篇',
  'medium': '中篇',
  'short': '短篇',
  'dialogue': '对话',
  'ip_collab': 'IP 联动',
};
const _formOrder = ['long', 'medium', 'short', 'dialogue', 'ip_collab'];

/// series → 中文系列名（头部要说清这届挂在哪条线上）。
const _seriesLabels = {
  'x': 'X征',
  'spring': '春季征文',
  'autumn': '秋季征文',
  'winter': '冬季征文',
  'other': '主题征文',
};

/// 档案正文一行数据（赛项行 / 动作行共用外壳，数字口径各说各的）。
class _RowData {
  final String title;
  final String? value;
  final IconData? icon;
  final bool enabled;
  final VoidCallback? onTap;

  const _RowData({
    required this.title,
    this.value,
    this.icon,
    this.enabled = true,
    this.onTap,
  });
}

class _Body extends ConsumerWidget {
  final String name;
  final ScrollController scroll;

  const _Body({
    required this.name,
    required this.scroll,
  });

  /// 打开官方活动页（外部浏览器；与详情页「打开官方页面」同一
  /// externalApplication 口径，docs/15 登记的 Icons.open_in_new 语义）。
  Future<void> _openOfficial(BuildContext context, String url) async {
    var ok = false;
    try {
      ok = await launchUrl(Uri.parse(url),
          mode: LaunchMode.externalApplication);
    } catch (_) {}
    if (!context.mounted || ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('无法打开官方活动页')),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final groups = ref.watch(contestArchiveProvider);
    final books = ref.watch(contestArchiveBooksProvider(name));
    return groups.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            '赛事档案加载失败：$e',
            style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
          ),
        ),
      ),
      data: (list) {
        ContestGroup? group;
        for (final g in list) {
          if (g.name == name) {
            group = g;
            break;
          }
        }
        return ListView(
          controller: scroll,
          padding: const EdgeInsets.only(bottom: 32),
          children: [
            _Header(group: group),
            // 2026-11-26 重排（用户裁定）：动作区紧跟头部——「这一届的书」
            // 是本页的出口，先给出口再给内容；获奖紧随其后。
            if (group != null) _actions(context, group),
            books.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '代表作加载失败：$e',
                  style: TextStyle(
                    fontSize: 13,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ),
              data: (res) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _awardsEntry(context, res.awards),
                  if (group != null && group.divisions.length > 1)
                    _divisions(context, group),
                  _represents(context, res.items),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  /// 获奖作品入口行（用户裁定 2026-11-26）：不再内联名单——入口行带
  /// 条数，点行进独立列表页（/contests/awards，通用榜单行渲染）。
  /// 无已核实获奖时整行不画。
  Widget _awardsEntry(BuildContext context, List<ContestAward> awards) {
    if (awards.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _section(context, '获奖作品', '官方已核实 · 按奖项等级排序'),
        _rows(context, [
          _RowData(
            title: '获奖作品名单',
            value: '${fmtCount(awards.length)} 条',
            onTap: () => context.push(
              '/contests/awards?c=${Uri.encodeComponent(name)}',
            ),
          ),
        ]),
      ],
    );
  }

  /// 代表作：各 form 头部窗口（引擎 per-form 开窗，按 favs 排）。在库
  /// 0 本时整块不渲染——覆盖率那行已经说过「清单是唯一书目来源」。
  /// 只有一种形态时不画形态小标题（用户裁定 2026-11-26）。
  Widget _represents(BuildContext context, List<RankItem> items) {
    final scheme = Theme.of(context).colorScheme;
    if (items.isEmpty) return const SizedBox.shrink();
    final byForm = <String, List<RankItem>>{};
    for (final it in items) {
      byForm.putIfAbsent(it.form, () => []).add(it);
    }
    final forms = _formOrder
        .where((f) => (byForm[f] ?? const []).isNotEmpty)
        .toList();
    final showSubhead = forms.length > 1;
    final summary =
        forms.map((f) => '${_formLabels[f]} ${byForm[f]!.length}').join(' · ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _section(context, '代表作', '按同世代收藏分位排序 · $summary'),
        for (final f in forms) ...[
          if (showSubhead)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
              child: Text(
                _formLabels[f]!,
                style: TextStyle(fontSize: 11.5, color: scheme.secondary),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: [
                // 序号变体（用户裁定 2026-11-27）：代表作带衬线排名序号。
                for (final it in byForm[f]!)
                  BookRowTile(item: it, showRank: true),
              ],
            ),
          ),
        ],
      ],
    );
  }

  /// 赛项区（≥2 轨）：一行一赛道，右数 = 该赛道官方清单条数，点行进对应
  /// 清单。赛道数与在库形态不同源（种子标签与官方分轨命名并非一一对应），
  /// 所以行里不并在库小字——硬凑映射就是假数。
  /// 获奖事件（一/二/三征）同区换口径：每行是一个奖项，右数是获奖名额，
  /// 点行进获奖名单。
  Widget _divisions(BuildContext context, ContestGroup g) {
    final award = g.listKind == 'award';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _section(
            context,
            award ? '奖项' : '赛项',
            award ? '数字为该奖项获奖名额 · 点行看获奖名单' : '数字为该赛道官方清单条数 · 点行看清单'),
        _rows(context, [
          for (final d in g.divisions)
            _RowData(
              title: d.name,
              value: fmtCount(d.isAward ? d.awards : d.roster),
              onTap: () => context.push('/contests/roster'
                  '?c=${Uri.encodeComponent(g.name)}'
                  '&d=${Uri.encodeComponent(d.name)}'),
            ),
        ]),
      ],
    );
  }

  /// 动作区（两行一事 + 右侧带数）：旧版三个整宽按钮叠放，且
  /// 「浏览全部作品」与「查看官方清单」字面看不出区别——数上来就分开了。
  /// 官方清单入口在无 tagId 时置灰而非隐藏：引擎会回落库内子集，但回落
  /// 页信息量不比本页多，别把它说成能用。获奖事件（listKind=award）把
  /// 入口换成「获奖名单」，值取获奖名额——参赛清单上游从未公布。
  Widget _actions(BuildContext context, ContestGroup g) {
    final url = g.official;
    final award = g.listKind == 'award';
    final String hint;
    if (award) {
      hint = '在库走榜单，获奖名单含库外作品';
    } else if (g.roster) {
      hint = '在库走榜单，官方清单含库外作品';
    } else {
      hint = '仅内置库（无官方清单接口）';
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _section(context, '这一届的书', hint),
        _rows(context, [
          _RowData(
            title: '浏览在库作品',
            value: g.count == 0 ? '库里还没有' : '${fmtCount(g.count)} 本',
            enabled: g.count > 0,
            onTap: () => context.push(
              '/browse?mode=contest&c=${Uri.encodeComponent(name)}',
            ),
          ),
          if (award)
            _RowData(
              title: '获奖名单',
              value: g.awardTotal == null
                  ? '名额未核实'
                  : fmtCount(g.awardTotal),
              enabled: true,
              onTap: () => context.push(
                '/contests/roster?c=${Uri.encodeComponent(name)}',
              ),
            )
          else
            _RowData(
              title: '官方清单',
              value: g.rosterTotal == null
                  ? (g.roster ? '条数未核实' : '接口无清单')
                  : '${fmtCount(g.rosterTotal)} 条',
              enabled: g.roster,
              onTap: () => context.push(
                '/contests/roster?c=${Uri.encodeComponent(name)}',
              ),
            ),
          if (url != null && url.isNotEmpty)
            _RowData(
              title: '官方活动页',
              icon: Icons.open_in_new,
              onTap: () => _openOfficial(context, url),
            ),
        ]),
      ],
    );
  }

  Widget _rows(BuildContext context, List<_RowData> rows) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          for (final (i, r) in rows.indexed) _row(context, r, first: i == 0),
        ],
      ),
    );
  }

  /// 一行一事：左标题 + 右数值 + 箭头。禁用行不画箭头（点了没反应的东西
  /// 不该看起来可点）。
  Widget _row(BuildContext context, _RowData r, {required bool first}) {
    final scheme = Theme.of(context).colorScheme;
    final muted = r.enabled ? scheme.onSurfaceVariant : scheme.outline;
    return Column(
      children: [
        if (!first) Divider(height: 1, color: scheme.outlineVariant),
        InkWell(
          onTap: r.enabled ? r.onTap : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                if (r.icon != null) ...[
                  Icon(r.icon, size: 16, color: muted),
                  const SizedBox(width: 8),
                ],
                Text(
                  r.title,
                  style: TextStyle(
                    fontSize: 13.5,
                    color: r.enabled ? scheme.onSurface : scheme.outline,
                  ),
                ),
                const Spacer(),
                Text(r.value ?? '', style: TextStyle(fontSize: 12, color: muted)),
                if (r.enabled)
                  Icon(Icons.chevron_right, size: 18, color: scheme.outline),
              ],
            ),
          ),
        ),
      ],
    );
  }

  static Widget _section(BuildContext context, String title, String hint) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Text(
            title,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              hint,
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

/// 档案头部：元信息行 → 赛程单行 → 库内覆盖率 → 台账备注。
class _Header extends StatelessWidget {
  final ContestGroup? group;

  const _Header({required this.group});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final g = group;
    if (g == null) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
        child: Text(
          '数据加载中',
          style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _meta(g),
            style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 10),
          _Schedule(group: g),
          const SizedBox(height: 12),
          _coverage(context, scheme, g),
          if (g.note != null) ...[
            const SizedBox(height: 8),
            Text(g.note!,
                style: TextStyle(fontSize: 11, color: scheme.tertiary)),
          ],
        ],
      ),
    );
  }

  /// 元信息行：年份（官方优先，缺则退在库年份区间）· 系列 · 在库形态。
  static String _meta(ContestGroup g) {
    final parts = <String>[
      g.year != null
          ? '${g.year} 年'
          : (g.yearMin == g.yearMax
              ? '在库年份 ${g.yearMin}'
              : '在库年份 ${g.yearMin}–${g.yearMax}'),
      _seriesLabels[g.series] ?? g.series,
    ];
    final forms = _formOrder
        .where((f) => (g.forms[f] ?? 0) > 0)
        .map((f) => '${_formLabels[f]} ${g.forms[f]}')
        .join(' · ');
    if (forms.isNotEmpty) parts.add('在库形态 $forms');
    return parts.join(' · ');
  }

  /// 库内覆盖率：在库 / 官方清单（2026-11-26 瘦身：规模三数块已删，
  /// 数字直接标在条两端——同一组数只在这里说一次）。
  Widget _coverage(BuildContext context, ColorScheme scheme, ContestGroup g) {
    final off = g.rosterTotal;
    if (off == null || off == 0) {
      if (g.listKind == 'award') {
        return Text(
          '这一届官方只公布获奖名单（名额 ${fmtCount(g.awardTotal)}），'
              '内置库有 ${fmtCount(g.count)} 本。',
          style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
        );
      }
      return Text(
        g.roster
            ? '这一届的官方清单条数未核实，清单入口照常可开。'
            : '这一届没有参赛清单接口，页面只有内置库里的作品。',
        style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
      );
    }
    if (g.count == 0) {
      return Text(
        '本地在库 0 本：这届没进种子，官方清单是它唯一的书目来源。',
        style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
      );
    }
    final ratio = (g.count / off).clamp(0.0, 1.0);
    final out = off - g.count;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('在库 ${fmtCount(g.count)}',
                style: TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant)),
            Text('官方清单 ${fmtCount(off)}',
                style: TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant)),
          ],
        ),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: ratio,
            minHeight: 6,
            backgroundColor: scheme.surfaceContainerHighest,
            color: scheme.secondary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          out > 0
              ? '库内覆盖 ${(ratio * 100).toStringAsFixed(1)}%，清单还有 '
                  '${fmtCount(out)} 条不在库内。'
              : '库内已覆盖官方清单全部 ${fmtCount(off)} 条。',
          style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
        ),
      ],
    );
  }
}

/// 赛程单行（2026-11-26 瘦身，用户裁定）：归档页是回看场景，三行竖向
/// 时间轴占地低价值——各段按 投稿开始 → 截止 → 公布 拼一行，缺段省略；
/// 结果日在未来标「预计」。全缺 → 「官方未公示赛程日期」。
class _Schedule extends StatelessWidget {
  final ContestGroup group;

  const _Schedule({required this.group});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final parts = <String>[];
    void add(String? raw, String label) {
      if (raw == null) return;
      final d = DateTime.parse(raw);
      final ds =
          '${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      final suffix =
          !d.isAfter(today) || label != '结果公布' ? '' : '（预计）';
      parts.add('$label $ds$suffix');
    }

    add(group.start, '投稿开始');
    add(group.end, '投稿截止');
    add(group.result, '结果公布');
    if (parts.isEmpty) {
      return Text(
        '官方未公示赛程日期',
        style: TextStyle(fontSize: 11.5, color: scheme.outline),
      );
    }
    return Text(
      parts.join('  →  '),
      style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
    );
  }
}
