import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'api.dart';
import 'job_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  final Settings settings;
  const HomeScreen({super.key, required this.settings});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Settings get s => widget.settings;
  String? path;
  String? name;
  bool uploading = false;

  Future<void> pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.video);
    final f = r?.files.single;
    if (f?.path != null) setState(() { path = f!.path; name = f.name; });
  }

  Future<void> start() async {
    if (path == null) return;
    await s.save();
    setState(() => uploading = true);
    try {
      final id = await Api(s).createJob(path!);
      if (!mounted) return;
      await Navigator.push(context, MaterialPageRoute(builder: (_) => JobScreen(settings: s, id: id)));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
    if (mounted) setState(() => uploading = false);
  }

  Widget dropdown(String label, String value, List<String> items, ValueChanged<String> on) {
    return DropdownButtonFormField<String>(
      value: items.contains(value) ? value : items.first,
      decoration: InputDecoration(labelText: label),
      items: [for (final e in items) DropdownMenuItem(value: e, child: Text(e))],
      onChanged: (v) { if (v != null) setState(() => on(v)); },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dubber ខ្មែរ'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () async {
              await Navigator.push(context, MaterialPageRoute(builder: (_) => SettingsScreen(settings: s)));
              setState(() {});
            },
          ),
        ],
      ),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Card(
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: uploading ? null : pick,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 16),
              child: Column(children: [
                Icon(path == null ? Icons.video_library_outlined : Icons.check_circle, size: 48,
                    color: Theme.of(context).colorScheme.primary),
                const SizedBox(height: 12),
                Text(name ?? 'ចុចដើម្បីជ្រើសវីដេអូ', textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 16)),
              ]),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: dropdown('ភាសាដើម', s.src, ['Auto', ...languages], (v) => s.src = v)),
          const SizedBox(width: 12),
          Expanded(child: dropdown('បកប្រែទៅ', s.tgt, languages, (v) => s.tgt = v)),
        ]),
        const SizedBox(height: 16),
        const Text('ប្រភេទបកប្រែ', style: TextStyle(color: Colors.white70)),
        const SizedBox(height: 6),
        SegmentedButton<String>(
          segments: [
            const ButtonSegment(value: 'free', label: Text('Free (លឿន)')),
            ButtonSegment(value: 'gemini', label: const Text('Gemini (ត្រឹមត្រូវ)'), enabled: s.hasKey),
          ],
          selected: {s.hasKey ? s.engine : 'free'},
          onSelectionChanged: (v) => setState(() => s.engine = v.first),
        ),
        if (!s.hasKey)
          const Padding(
            padding: EdgeInsets.only(top: 6),
            child: Text('ដាក់ Gemini API Key ក្នុង ⚙ Settings ដើម្បីប្រើ Gemini', style: TextStyle(color: Colors.white54, fontSize: 12)),
          ),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(child: dropdown('ស្តាប់សំឡេង (STT)', s.hasKey ? s.stt : 'whisper', s.hasKey ? ['whisper', 'gemini'] : ['whisper'], (v) => s.stt = v)),
          const SizedBox(width: 12),
          Expanded(child: dropdown('Whisper size', s.whisper, ['tiny', 'base', 'small', 'medium'], (v) => s.whisper = v)),
        ]),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('⚡ ម៉ូដលឿន (Gemini Lite · បកខ្លី)'),
          subtitle: Text(
            s.hasKey ? 'បកប្រែលឿន ប្រយោគខ្លី និយាយទាន់ពេលវីដេអូ' : 'ត្រូវការ Gemini API Key ក្នុង ⚙ Settings',
            style: const TextStyle(fontSize: 12),
          ),
          value: s.hasKey && s.fast,
          onChanged: s.hasKey
              ? (v) => setState(() {
                    s.fast = v;
                    if (v) {
                      s.engine = 'gemini';
                      s.stt = 'gemini';
                    }
                  })
              : null,
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: (path == null || uploading) ? null : start,
          icon: uploading
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.auto_awesome),
          label: Text(uploading ? 'កំពុង Upload…' : '⚡ Transcribe + Translate'),
          style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
        ),
      ]),
    );
  }
}
