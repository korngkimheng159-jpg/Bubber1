import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'package:video_player/video_player.dart';
import 'api.dart';

class JobScreen extends StatefulWidget {
  final Settings settings;
  final String id;
  const JobScreen({super.key, required this.settings, required this.id});

  @override
  State<JobScreen> createState() => _JobScreenState();
}

class _JobScreenState extends State<JobScreen> {
  late final Api api = Api(widget.settings);
  Timer? timer;
  bool polling = false;

  String status = 'queued', msg = '', error = '';
  int pct = 0;

  List<Seg> segs = [];
  List<TextEditingController> ctl = [];

  double speed = 1.0;
  String fit = 'Soft';
  bool keepBg = false;
  int res = 0;

  VideoPlayerController? vc;
  String? file;

  @override
  void initState() {
    super.initState();
    poll();
    startTimer();
  }

  void startTimer() {
    timer?.cancel();
    timer = Timer.periodic(const Duration(milliseconds: 1500), (_) => poll());
  }

  @override
  void dispose() {
    timer?.cancel();
    vc?.dispose();
    for (final c in ctl) { c.dispose(); }
    super.dispose();
  }

  Future<void> poll() async {
    if (polling) return;
    polling = true;
    try {
      final j = await api.status(widget.id);
      if (!mounted) return;
      final st = j['status'] as String;
      setState(() {
        status = st;
        pct = (j['pct'] as num).toInt();
        msg = (j['msg'] ?? '') as String;
        error = (j['error'] ?? '') as String;
      });
      if (st == 'review' && segs.isEmpty) loadSegs(j['segments'] as List);
      if (st == 'review' || st == 'error' || st == 'done') timer?.cancel();
      if (st == 'done') await fetchVideo();
    } catch (_) {
      // short network drop: keep polling
    } finally {
      polling = false;
    }
  }

  void loadSegs(List raw) {
    for (final c in ctl) { c.dispose(); }
    segs = [for (final e in raw) Seg.fromJson(Map<String, dynamic>.from(e as Map))];
    ctl = [for (final s in segs) TextEditingController(text: s.text)];
    setState(() {});
  }

  Future<void> fetchVideo() async {
    try {
      final path = await api.download(widget.id);
      final old = vc;
      final c = VideoPlayerController.file(File(path));
      await c.initialize();
      c.setLooping(true);
      if (!mounted) { c.dispose(); return; }
      setState(() { vc = c; file = path; });
      old?.dispose();
    } catch (e) {
      if (mounted) setState(() { error = '$e'; });
    }
  }

  Future<void> render() async {
    for (var i = 0; i < segs.length; i++) { segs[i].text = ctl[i].text; }
    try {
      await api.render(widget.id, segs, speed: speed, fit: fit, keepBg: keepBg, res: res);
      vc?.pause();
      setState(() { status = 'working'; pct = 0; msg = 'Generate voice…'; error = ''; });
      startTimer();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  String t(double sec) {
    final m = sec ~/ 60, s = (sec % 60).floor();
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final working = status == 'queued' || status == 'working';
    final review = status == 'review' || (status == 'error' && segs.isNotEmpty);
    return Scaffold(
      appBar: AppBar(
        title: Text(status == 'done' ? '✔ រួចរាល់' : review ? 'ពិនិត្យ និងកែអត្ថបទ' : 'កំពុងដំណើរការ'),
        actions: [
          if (status == 'done' && segs.isNotEmpty)
            TextButton(onPressed: () => setState(() => status = 'review'), child: const Text('កែអត្ថបទ')),
        ],
      ),
      body: working ? progressView() : status == 'done' ? resultView() : review ? reviewView() : errorView(),
    );
  }

  Widget progressView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('$pct%', style: const TextStyle(fontSize: 48, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            LinearProgressIndicator(value: pct == 0 ? null : pct / 100, minHeight: 8),
            const SizedBox(height: 16),
            Text(msg, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 8),
            const Text('អាចទុកអេក្រង់បើកចោលបាន', style: TextStyle(color: Colors.white38, fontSize: 12)),
          ]),
        ),
      );

  Widget errorView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.redAccent),
            const SizedBox(height: 12),
            Text(error.isEmpty ? 'មានបញ្ហា' : error, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(onPressed: () => Navigator.pop(context), child: const Text('ត្រឡប់ក្រោយ')),
          ]),
        ),
      );

  Widget reviewView() {
    return Column(children: [
      if (error.isNotEmpty)
        Container(
          width: double.infinity,
          color: Colors.red.withAlpha(60),
          padding: const EdgeInsets.all(10),
          child: Text(error, style: const TextStyle(fontSize: 12)),
        ),
      Expanded(
        child: ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: segs.length + 1,
          itemBuilder: (_, i) {
            if (i == 0) return optionsCard();
            final k = i - 1, s = segs[k];
            final male = s.gender.startsWith('m');
            return Card(
              margin: const EdgeInsets.only(bottom: 10),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Text('${k + 1}  ${t(s.start)} → ${t(s.end)}', style: const TextStyle(color: Colors.white54, fontSize: 12)),
                    const Spacer(),
                    InkWell(
                      onTap: () => setState(() => s.gender = male ? 'female' : 'male'),
                      child: Chip(
                        avatar: Icon(male ? Icons.male : Icons.female, size: 16),
                        label: Text(male ? 'ប្រុស' : 'ស្រី'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ]),
                  if (s.src.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Text(s.src, style: const TextStyle(color: Colors.white60)),
                    ),
                  TextField(controller: ctl[k], minLines: 1, maxLines: 5),
                ]),
              ),
            );
          },
        ),
      ),
      SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: render,
              icon: const Icon(Icons.record_voice_over),
              label: const Text('🔊 បង្កើតសំឡេង + Export'),
              style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
            ),
          ),
        ),
      ),
    ]);
  }

  Widget optionsCard() => Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: ExpansionTile(
          title: const Text('ជម្រើសសំឡេង / វីដេអូ'),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          children: [
            Row(children: [
              const Text('ល្បឿនសំឡេង'),
              Expanded(
                child: Slider(
                  value: speed, min: 0.7, max: 1.5, divisions: 8, label: '${speed.toStringAsFixed(2)}×',
                  onChanged: (v) => setState(() => speed = v),
                ),
              ),
            ]),
            DropdownButtonFormField<String>(
              value: fit,
              decoration: const InputDecoration(labelText: 'Auto-Fit (សំឡេងឲ្យចូលពេល)'),
              items: const [
                DropdownMenuItem(value: 'Off', child: Text('Off')),
                DropdownMenuItem(value: 'Soft', child: Text('Soft')),
                DropdownMenuItem(value: 'Hard', child: Text('Hard')),
              ],
              onChanged: (v) => setState(() => fit = v ?? 'Soft'),
            ),
            const SizedBox(height: 10),
            DropdownButtonFormField<int>(
              value: res,
              decoration: const InputDecoration(labelText: 'គុណភាព'),
              items: const [
                DropdownMenuItem(value: 0, child: Text('ដើម')),
                DropdownMenuItem(value: 720, child: Text('720p')),
                DropdownMenuItem(value: 1080, child: Text('1080p')),
              ],
              onChanged: (v) => setState(() => res = v ?? 0),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('រក្សាសំឡេងដើមស្រាលៗ'),
              value: keepBg,
              onChanged: (v) => setState(() => keepBg = v),
            ),
          ],
        ),
      );

  Widget resultView() {
    final c = vc;
    return ListView(padding: const EdgeInsets.all(16), children: [
      if (c == null || !c.value.isInitialized)
        const Padding(padding: EdgeInsets.all(48), child: Center(child: CircularProgressIndicator()))
      else ...[
        ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: AspectRatio(aspectRatio: c.value.aspectRatio, child: VideoPlayer(c)),
        ),
        VideoProgressIndicator(c, allowScrubbing: true),
        const SizedBox(height: 8),
        Center(
          child: IconButton.filled(
            iconSize: 36,
            onPressed: () => setState(() => c.value.isPlaying ? c.pause() : c.play()),
            icon: Icon(c.value.isPlaying ? Icons.pause : Icons.play_arrow),
          ),
        ),
      ],
      const SizedBox(height: 16),
      FilledButton.icon(
        onPressed: file == null ? null : () => Share.shareXFiles([XFile(file!)], text: 'Dubbed video'),
        icon: const Icon(Icons.share),
        label: const Text('Share / Save'),
        style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
      ),
      const SizedBox(height: 10),
      OutlinedButton(onPressed: () => Navigator.pop(context), child: const Text('វីដេអូថ្មី')),
    ]);
  }
}
