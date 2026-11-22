import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_card.dart';

/// 单届赛事档案（docs/contest-display-in-app.md 形态一）：本地零请求视图。
///
/// 头部 = 官方赛程（引擎内嵌用户核实静态表；缺失只显届次/年份，不编造）+
/// 在库 form 分布；代表作 = 各 form 头部窗口，按同世代收藏分位（fav_pctl）
/// 排序（docs/12 红线：累计原始值不进排序）。
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

class _Body extends ConsumerWidget {
  final String name;
  final ScrollController scroll;

  const _Body({
    required this.name,
    required this.scroll,
  });

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
              data: (res) {
                final byForm = <String, List<RankItem>>{};
                for (final it in res.items) {
                  byForm.putIfAbsent(it.form, () => []).add(it);
                }
                final children = <Widget>[];
                for (final f in _formOrder) {
                  final section = byForm[f];
                  if (section == null || section.isEmpty) continue;
                  children.add(Padding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 2),
                    child: Row(
                      children: [
                        Text(
                          _formLabels[f]!,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          '代表作 ${section.length}',
                          style: TextStyle(
                            fontSize: 11,
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ));
                  children.add(Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Column(
                      children: [
                        for (final it in section) BookRowCard(item: it),
                      ],
                    ),
                  ));
                }
                // 获奖作品区块（schema v5，docs §6）：该届库内获奖书，行序
                // = 引擎 fav_pctl 同代分位；奖项仅徽标展示、不参与排序。
                // 映射表外赛事返回空列表 → 区块隐藏。
                if (res.awards.isNotEmpty) {
                  children.add(Padding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 2),
                    child: Row(
                      children: [
                        Text(
                          '获奖作品',
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          '${res.awards.length} 本（库内）',
                          style: TextStyle(
                            fontSize: 11,
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ));
                  children.add(Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Column(
                      children: [
                        for (final a in res.awards) _AwardRow(a: a),
                      ],
                    ),
                  ));
                }
                return Column(children: children);
              },
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => context.push(
                    '/browse?mode=contest&c=${Uri.encodeComponent(name)}',
                  ),
                  child: const Text('浏览全部作品'),
                ),
              ),
            ),
            // 官方清单入口（形态二，按需）：无 tagId / 接口失效时由引擎
            // 回落库内子集，页面内提示「仅库内作品」，入口恒在。
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => context.push(
                    '/contests/roster?c=${Uri.encodeComponent(name)}',
                  ),
                  child: const Text('查看官方清单'),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                '代表作按同世代收藏分位排序，累计收藏仅展示；'
                '上方计数为在库规模，官方参赛规模见「查看官方清单」。',
                style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _Header extends StatelessWidget {
  final ContestGroup? group;

  const _Header({required this.group});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final g = group;
    final dateParts = <String>[];
    if (g != null) {
      if (g.start != null && g.end != null) {
        dateParts.add('官方赛程 ${g.start} → ${g.end}');
      } else if (g.start != null) {
        dateParts.add('官方启动 ${g.start}');
      } else if (g.year != null) {
        dateParts.add('官方启动 ${g.year}');
      }
      if (g.note != null) dateParts.add(g.note!);
      if (dateParts.isEmpty) {
        dateParts.add(g.yearMin == g.yearMax
            ? '在库年份 ${g.yearMin}'
            : '在库年份 ${g.yearMin}–${g.yearMax}');
      }
    } else {
      dateParts.add('数据加载中');
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            dateParts.join(' · '),
            style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
          ),
          if (g != null) ...[
            const SizedBox(height: 8),
            Text(
              _distribution(g),
              style: TextStyle(fontSize: 12, color: scheme.secondary),
            ),
            if (g.tracks.length > 1) ...[
              const SizedBox(height: 4),
              Text(
                '赛项：${g.tracks.join(' · ')}',
                style: TextStyle(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  static String _distribution(ContestGroup g) => _formOrder
      .where((f) => g.forms[f] != null)
      .map((f) => '${_formLabels[f]} ${g.forms[f]}')
      .join(' · ');
}

/// 获奖区块一行：徽标文案 + 书名/作者 + 收藏。点击 → 详情页（获奖详情在
/// 详情页徽标完整呈现，行内不重复展开）。
class _AwardRow extends StatelessWidget {
  final AwardBook a;

  const _AwardRow({super.key, required this.a});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push('/book/${a.award.nid}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: scheme.tertiaryContainer,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                a.award.displayAward,
                style: TextStyle(
                  fontSize: 11,
                  color: scheme.onTertiaryContainer,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    a.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    a.author,
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            if (a.favs != null)
              Text(
                '藏 ${a.favs}',
                style: TextStyle(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
