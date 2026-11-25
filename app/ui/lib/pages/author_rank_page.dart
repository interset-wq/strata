import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 作者榜页（docs/author-rank.md §9；用户 2026-11-25：home 状态入口换
/// 作者榜）。稳定产出的优质作者，按 form 隔离出页（无页内切换），数据是
/// seed v10 预构建表（运行时零计算）；行点击 → /author?author= 看该作者
/// 全部作品。App 只展示作者名 + 一本代表作（rep_nid/rep_title）。
class AuthorRankPage extends ConsumerStatefulWidget {
  /// 形式（与量化榜单同隔离原则）：长篇 tab 默认 'long'，其余 tab 传各自
  /// form。
  final String form;

  const AuthorRankPage({super.key, this.form = 'long'});

  @override
  ConsumerState<AuthorRankPage> createState() => _AuthorRankPageState();
}

class _AuthorRankPageState extends ConsumerState<AuthorRankPage> {
  List<AuthorRankItem> _items = [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final items = await handle.api.authorRanks(form: widget.form);
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  String get _title {
    switch (widget.form) {
      case 'dialogue':
        return '对话作者榜';
      case 'medium':
        return '中篇作者榜';
      case 'short':
        return '短篇作者榜';
      case 'ip_collab':
        return 'IP 作者榜';
      default:
        return '作者榜';
    }
  }

  String get _formName {
    switch (widget.form) {
      case 'dialogue':
        return '对话';
      case 'medium':
        return '中篇';
      case 'short':
        return '短篇';
      case 'ip_collab':
        return 'IP';
      default:
        return '长篇';
    }
  }

  void _showAbout() {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('榜单依据'),
        content: SizedBox(
          width: 320,
          child: Text(
            '选出「稳定产出的优质作者」：\n'
            '· 入榜 = 本 form（$_formName）有效作品 ≥ 3 本\n'
            '· 排名 = 信赖加权分：代表作 top3 收藏和 × 完结率折扣\n'
            '· form 隔离：只按本 form 作品计算，同一作者可同时出现在其他 form 榜\n'
            '· 中短篇榜内作品必然已完结（连载/假完结已剔除）\n'
            '· 本榜不覆盖全库作者（「稳定作者榜」，非全量目录）\n\n'
            '点作者进 TA 的全部作品页（含库外书）。',
            style: const TextStyle(fontSize: 12, height: 1.6),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          IconButton(
            tooltip: '榜单依据',
            icon: const Icon(Icons.info_outline),
            onPressed: _showAbout,
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _error != null && _items.isEmpty
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text('加载失败：$_error',
                      style:
                          TextStyle(color: scheme.error, fontSize: 13)),
                ),
              )
            : _loading && _items.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 8),
                    itemCount: _items.length,
                    itemBuilder: (context, i) {
                      final a = _items[i];
                      final hot = a.rankNo <= 3;
                      return InkWell(
                        onTap: () => context.push(
                            '/author?author=${Uri.encodeComponent(a.author)}'),
                        borderRadius: BorderRadius.circular(12),
                        child: Container(
                          margin: const EdgeInsets.symmetric(vertical: 3),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 10),
                          color: scheme.surface,
                          child: Row(
                            children: [
                              Container(
                                width: 28,
                                height: 28,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: hot
                                      ? scheme.primary
                                      : scheme.surfaceContainerHighest,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  '${a.rankNo}',
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: hot
                                        ? scheme.onPrimary
                                        : scheme.onSurfaceVariant,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(a.author,
                                        style: const TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w600)),
                                    const SizedBox(height: 2),
                                    Text('代表作 · ${a.repTitle}',
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                            fontSize: 11,
                                            color:
                                                scheme.onSurfaceVariant)),
                                  ],
                                ),
                              ),
                              Icon(Icons.chevron_right,
                                  size: 18, color: scheme.onSurfaceVariant),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
      ),
    );
  }
}
