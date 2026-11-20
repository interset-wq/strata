import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../app/theme.dart';
import '../data/api/strata_api.dart';
import 'book_row_tile.dart';
import 'default_cover.dart';
import 'metric_badge.dart';

/// 纸墨封面合成 banner（对话 tab 轮播专用）。
///
/// dialogue 形态池没有 featured 定制图，端上用封面实时合成：
/// 右侧完整 3:4 封面，左侧封面高斯模糊 + ~85% 纸色薄纱，
/// 朱砂印记 + 衬线粗体书名 + 著者行 + 字数/收藏指标行。
/// 与 BannerCarousel 同 2.2 宽高比，切 tab 轮播高度不跳。
class CoverBannerCard extends StatelessWidget {
  final RankItem item;
  final VoidCallback? onTap;

  const CoverBannerCard({super.key, required this.item, this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = coverImageUrl(item.coverUrl);
    final hasCover = coverUrl != null;
    // 纸墨色板：纸底=页面背景色、墨字/灰褐=主题墨阶、朱砂=品牌红。
    final paper = scheme.surfaceContainerHighest;
    final ink = scheme.onSurface;
    final ink2 = scheme.onSurfaceVariant;

    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: AspectRatio(
          aspectRatio: 2.2,
          child: Row(
            children: [
              // 左：模糊封面 + 纸纱 + 文字
              Expanded(
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    ColoredBox(color: paper),
                    if (hasCover) _BlurredCover(url: coverUrl),
                    // ~85% 纸纱：封面只剩 15% 色调透出，是纸不是玻璃。
                    ColoredBox(color: paper.withValues(alpha: .85)),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 10, 10, 10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 朱砂印记 + 衬线书名
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Container(
                                width: 5,
                                height: 20,
                                margin: const EdgeInsets.only(top: 4, right: 7),
                                decoration: BoxDecoration(
                                  color: scheme.primary,
                                  borderRadius: BorderRadius.circular(2),
                                ),
                              ),
                              Expanded(
                                child: Text(
                                  '《${item.title}》',
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    fontFamily: StrataTokens.serif,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 15,
                                    letterSpacing: .5,
                                    color: ink,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 5),
                          Text(
                            '著 · ${item.author}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 10, color: ink2),
                          ),
                          const Spacer(),
                          // 指标行：字数 + 收藏（seed 无简介字段，用指标语言）
                          FittedBox(
                            fit: BoxFit.scaleDown,
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (item.words != null)
                                  MetricBadge(
                                    icon: MetricIcons.words,
                                    text: '${BookRowTile.wan(item.words)}字',
                                  ),
                                if (item.words != null && item.favs > 0)
                                  const SizedBox(width: 8),
                                if (item.favs > 0)
                                  MetricBadge(
                                    icon: MetricIcons.favs,
                                    text: BookRowTile.wan(item.favs),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              // 右：完整 3:4 封面，满高
              AspectRatio(
                aspectRatio: 3 / 4,
                child: hasCover
                    ? CachedNetworkImage(
                        imageUrl: coverUrl,
                        fit: BoxFit.cover,
                        placeholder: (_, _) =>
                            const ColoredBox(color: Color(0x59B8AE9E)),
                        errorWidget: (_, _, _) =>
                            _CoverPlaceholder(scheme: scheme),
                      )
                    : _CoverPlaceholder(scheme: scheme),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CoverPlaceholder extends StatelessWidget {
  final ColorScheme scheme;

  const _CoverPlaceholder({required this.scheme});

  @override
  Widget build(BuildContext context) {
    // 引擎保证有封面 URL；这里是 CDN 404 的兜底占位（docs/15 占位语义）。
    return ColoredBox(
      color: scheme.surfaceContainerHighest,
      child: Center(
        child: Icon(Icons.image_not_supported_outlined,
            size: 32, color: scheme.outline),
      ),
    );
  }
}

/// 封面高斯模糊层：异步取图（与右侧封面共享缓存，不额外发请求），
/// 就绪后 CustomPaint 画 blur 的 cover-fit 图。纸色底在其下，
/// 图没加载完时视觉上是纯纸底，无跳变。
class _BlurredCover extends StatefulWidget {
  final String url;

  const _BlurredCover({required this.url});

  @override
  State<_BlurredCover> createState() => _BlurredCoverState();
}

class _BlurredCoverState extends State<_BlurredCover> {
  ui.Image? _image;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final completer = Completer<ui.Image>();
      NetworkImage(widget.url).resolve(ImageConfiguration.empty).addListener(
        ImageStreamListener(
          (info, _) {
            if (!completer.isCompleted) completer.complete(info.image);
          },
          onError: (e, _) {
            if (!completer.isCompleted) completer.completeError(e);
          },
        ),
      );
      try {
        final image = await completer.future;
        if (!mounted) return;
        setState(() => _image = image);
      } catch (_) {
        // 404 时保持纸底，右侧封面区域另有占位。
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final image = _image;
    if (image == null) return const SizedBox.shrink();
    return CustomPaint(
      size: Size.infinite,
      painter: _BlurCoverPainter(image),
    );
  }
}

class _BlurCoverPainter extends CustomPainter {
  final ui.Image image;

  _BlurCoverPainter(this.image);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..filterQuality = FilterQuality.medium
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, 24);
    // cover-fit：等比放大铺满，居中裁切
    final scale = math.max(size.width / image.width, size.height / image.height);
    final sw = size.width / scale;
    final sh = size.height / scale;
    final src = Rect.fromLTWH(
        (image.width - sw) / 2, (image.height - sh) / 2, sw, sh);
    canvas.drawImageRect(image, src, Offset.zero & size, paint);
  }

  @override
  bool shouldRepaint(_BlurCoverPainter oldDelegate) =>
      oldDelegate.image != image;
}

/// 对话 tab 轮播：CoverBannerCard 的无限自动轮播（4s 前翻、手势重置计时、
/// 指示点），行为与 BannerCarousel 对齐；数据为静态收藏序，不随日期变。
class CoverBannerCarousel extends StatefulWidget {
  final List<RankItem> items;
  final void Function(RankItem item)? onTap;

  const CoverBannerCarousel({super.key, required this.items, this.onTap});

  @override
  State<CoverBannerCarousel> createState() => _CoverBannerCarouselState();
}

class _CoverBannerCarouselState extends State<CoverBannerCarousel> {
  // 无限副本：与 BannerCarousel 同款方案，自动播放恒 +1 同向前进。
  static const _loops = 1000;

  late final _controller = PageController(
      viewportFraction: 1, initialPage: _loops ~/ 2);
  int _page = 0;
  Timer? _auto;

  static const _autoInterval = Duration(seconds: 4);

  @override
  void initState() {
    super.initState();
    _restartAuto();
  }

  void _restartAuto() {
    _auto?.cancel();
    _auto = Timer.periodic(_autoInterval, (_) {
      if (!mounted || !_controller.hasClients || widget.items.length < 2) {
        return;
      }
      final next = _controller.page!.round() + 1;
      _controller.animateToPage(next,
          duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
    });
  }

  @override
  void dispose() {
    _auto?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.items.isEmpty) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 2.2, // 与 BannerCarousel 同高，切 tab 不跳
          child: NotificationListener<ScrollNotification>(
            onNotification: (n) {
              if (n is ScrollStartNotification ||
                  n is ScrollEndNotification) {
                _restartAuto();
              }
              return false;
            },
            child: PageView.builder(
              controller: _controller,
              itemCount: widget.items.length * _loops,
              onPageChanged: (i) =>
                  setState(() => _page = i % widget.items.length),
              itemBuilder: (context, i) {
                final it = widget.items[i % widget.items.length];
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: CoverBannerCard(
                    item: it,
                    onTap: () => widget.onTap?.call(it),
                  ),
                );
              },
            ),
          ),
        ),
        const SizedBox(height: 6),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < widget.items.length; i++)
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.symmetric(horizontal: 2.5),
                width: i == _page ? 14 : 5,
                height: 5,
                decoration: BoxDecoration(
                  color: i == _page
                      ? scheme.primary
                      : scheme.primary.withValues(alpha: .3),
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
