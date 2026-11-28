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
/// 2026-11-27 改版（用户裁定）：AppBar 只留奖杯（获奖记录）与 open_in_new
/// （官方活动页）两个 icon；头部压成元信息 + 在库覆盖一行，赛程由列表页
/// 承担；正文只保留代表作（每个 form 一组），参赛清单入口跟在标题右侧。
/// 获奖作品不铺正文（top10 基本覆盖获奖者），只走 AppBar 奖杯入口。
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
      appBar: AppBar(
        title: Text(widget.name),
        actions: [
          Consumer(
            builder: (context, ref, _) {
              ContestGroup? group;
              for (final g
                  in ref.watch(contestArchiveProvider).value ??
                      const <ContestGroup>[]) {
                if (g.name == widget.name) {
                  group = g;
                  break;
                }
              }
              final awards =
                  ref
                      .watch(contestArchiveBooksProvider(widget.name))
                      .value
                      ?.awards ??
                  const <ContestAward>[];
              final hasAwards =
                  awards.isNotEmpty || (group?.awardTotal ?? 0) > 0;
              final official = group?.official;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (hasAwards)
                    IconButton(
                      tooltip: '获奖记录',
                      icon: const Icon(Icons.emoji_events),
                      onPressed: () => context.push(
                        '/contests/awards?c=${Uri.encodeComponent(widget.name)}',
                      ),
                    ),
                  if (official != null && official.isNotEmpty)
                    IconButton(
                      tooltip: '官方活动页',
                      icon: const Icon(Icons.open_in_new),
                      onPressed: () => _openOfficial(context, official),
                    ),
                ],
              );
            },
          ),
        ],
      ),
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

/// 打开官方活动页（外部浏览器；与详情页「打开官方页面」同一
/// externalApplication 口径，docs/15 登记的 Icons.open_in_new 语义）。
Future<void> _openOfficial(BuildContext context, String url) async {
  var ok = false;
  try {
    ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  } catch (_) {}
  if (!context.mounted || ok) return;
  ScaffoldMessenger.of(context)
      .showSnackBar(const SnackBar(content: Text('无法打开官方活动页')));
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
  'autumn': '秋季/少年征文',
  'winter': '冬季征文',
  'other': '主题征文',
};

class _Body extends ConsumerWidget {
  final String name;
  final ScrollController scroll;

  const _Body({required this.name, required this.scroll});

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
              data: (res) => _represents(context, res.items, group),
            ),
          ],
        );
      },
    );
  }

  /// 代表作：引擎 per-form 开窗（默认每形态 10 本），按 favs 排。
  /// 清单入口与标题同一行，正文不再另设动作区。
  Widget _represents(
    BuildContext context,
    List<RankItem> items,
    ContestGroup? group,
  ) {
    final scheme = Theme.of(context).colorScheme;
    final roster = group?.roster ?? false;
    final rosterTotal = group?.rosterTotal;
    if (items.isEmpty) {
      // 在库 0 本不摆代表作，但参赛清单仍是唯一书目来源，入口不能一起消失。
      if (!roster) return const SizedBox.shrink();
      return Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
        child: Align(
          alignment: Alignment.centerRight,
          child: _rosterLink(context, scheme, rosterTotal),
        ),
      );
    }
    final byForm = <String, List<RankItem>>{};
    for (final it in items) {
      byForm.putIfAbsent(it.form, () => []).add(it);
    }
    final forms = _formOrder
        .where((f) => (byForm[f] ?? const []).isNotEmpty)
        .toList();
    final showSubhead = forms.length > 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 6),
          child: Row(
            children: [
              const Text(
                '代表作',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              if (roster) _rosterLink(context, scheme, rosterTotal),
            ],
          ),
        ),
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

  Widget _rosterLink(BuildContext context, ColorScheme scheme, int? total) {
    return InkWell(
      onTap: () =>
          context.push('/contests/roster?c=${Uri.encodeComponent(name)}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
        child: Text(
          total == null ? '参赛清单 →' : '参赛清单 ${fmtCount(total)} →',
          style: TextStyle(fontSize: 11, color: scheme.primary),
        ),
      ),
    );
  }
}

/// 档案头部：元信息 → 在库覆盖 → 台账备注。赛程由列表页承担，
/// 详情页不再重复；主体直接进入代表作。
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
          const SizedBox(height: 6),
          _coverage(scheme, g),
          if (g.note != null) ...[
            const SizedBox(height: 6),
            Text(
              g.note!,
              style: TextStyle(fontSize: 11, color: scheme.tertiary),
            ),
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
        .map((f) => _formLabels[f]!)
        .join(' / ');
    if (forms.isNotEmpty) parts.add(forms);
    return parts.join(' · ');
  }

  /// 库内覆盖：只留一行，数字细节交给代表作行的参赛清单入口。
  Widget _coverage(ColorScheme scheme, ContestGroup g) {
    final off = g.rosterTotal;
    final inLib = '在库 ${fmtCount(g.count)}';
    final String text;
    if (off == null || off == 0) {
      if (g.listKind == 'award') {
        text = '$inLib · 官方只公布获奖名单';
      } else if (g.roster) {
        text = '$inLib · 参赛清单条数未核实';
      } else {
        text = '$inLib · 无参赛清单接口';
      }
    } else {
      final ratio = (g.count / off).clamp(0.0, 1.0);
      text = '$inLib · 覆盖 ${(ratio * 100).toStringAsFixed(1)}%';
    }
    return Text(
      text,
      style: TextStyle(
        fontSize: 11.5,
        fontWeight: FontWeight.w500,
        color: scheme.onSurface,
      ),
    );
  }
}
