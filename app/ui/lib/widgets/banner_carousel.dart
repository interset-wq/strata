import 'dart:async';

import 'package:flutter/material.dart';

import '../data/api/strata_api.dart';

/// SFACG banner 源图 URL：4.47:1 超宽定制图（非书籍封面）。
/// 轮播与首页大图精选共用。
String bannerImageUrl(int nid) =>
    'https://rs.sfacg.com/web/novel/images/images/beitouNew/$nid.jpg';

/// banner cut 版：CDN 居中裁切成品图 750×430（1.744:1 ≈ 16:9），
/// 无需端上手动裁核心带。首页大图精选直接用。
String bannerCutUrl(int nid) =>
    'https://rs.sfacg.com/web/novel/images/images/beitouNew/cut/$nid.jpg';

/// cut 版成品图的宽高比（750×430），容器按此比例展示零裁切。
const double bannerCutAspect = 750 / 430;

/// 首页轮播：featured=1 编辑精选。
///
/// SFACG banner 源图为 4.47:1 超宽图（rs.sfacg.com beitouNew/{nid}.jpg），
/// 直接 BoxFit.cover 会裁掉两侧主体。沿用 novly 的偏移方案：手机宽度下
/// 按 1.45× 容器宽渲染、左移 0.45× 宽，把原图 35%~95% 的核心带对准容器。
class BannerCarousel extends StatefulWidget {
  final List<FeaturedItem> items;
  final void Function(FeaturedItem item)? onTap;

  const BannerCarousel({super.key, required this.items, this.onTap});

  @override
  State<BannerCarousel> createState() => _BannerCarouselState();
}

class _BannerCarouselState extends State<BannerCarousel> {
  // 无限副本：1000 份轮次、从中间副本起步，自动播放永远 +1 向前，
  // 末张→首张不会反向掉头（回绕靠副本边界无感衔接）。
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

  // 自动轮播：4s 翻下一页（副本序号恒 +1，始终同向）；用户手势翻页后重新计时。
  void _restartAuto() {
    _auto?.cancel();
    _auto = Timer.periodic(_autoInterval, (_) {
      if (!mounted || !_controller.hasClients || widget.items.length < 2) {
        return;
      }
      final next = _controller.page!.round() + 1;
      _controller.animateToPage(next,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOut);
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
          aspectRatio: 2.2, // ~0.45 高宽比；图片本体 4.47:1，经偏移裁剪取核心带
          child: NotificationListener<ScrollNotification>(
            onNotification: (n) {
              // 用户手势翻页：重启计时，避免自动翻页与手势打架
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
                  child: _Slide(
                    nid: it.nid,
                    title: it.title,
                    author: it.author,
                    url: bannerImageUrl(it.nid),
                    fallbackColor: scheme.primary.withValues(alpha: .15),
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

class _Slide extends StatefulWidget {
  final int nid;
  final String title;
  final String author;
  final String url;
  final Color fallbackColor;
  final VoidCallback onTap;

  const _Slide({
    required this.nid,
    required this.title,
    required this.author,
    required this.url,
    required this.fallbackColor,
    required this.onTap,
  });

  @override
  State<_Slide> createState() => _SlideState();
}

class _SlideState extends State<_Slide> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: LayoutBuilder(
          builder: (context, box) {
            final w = box.maxWidth;
            final h = box.maxHeight;
            return Stack(
              fit: StackFit.expand,
              children: [
                ColoredBox(color: widget.fallbackColor),
                // novly 偏移方案：1.45× 宽渲染 + 左移 0.45×，取超宽图核心带
                Positioned(
                  left: -w * 0.45,
                  width: w * 1.45,
                  top: 0,
                  height: h,
                  child: Image.network(
                    widget.url,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) => Center(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          widget.title,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(color: Colors.white),
                        ),
                      ),
                    ),
                  ),
                ),
                // 底部渐晕 + 标题/作者
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(14, 24, 14, 10),
                    decoration: const BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Colors.transparent, Color(0xB3140E08)],
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          widget.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                            fontSize: 14,
                          ),
                        ),
                        Text(
                          '${widget.author} · 编辑精选',
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 10,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

