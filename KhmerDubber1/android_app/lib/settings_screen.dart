import 'package:flutter/material.dart';
import 'api.dart';

class SettingsScreen extends StatefulWidget {
  final Settings settings;
  const SettingsScreen({super.key, required this.settings});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final server = TextEditingController(text: widget.settings.server);
  late final token = TextEditingController(text: widget.settings.token);
  late final key = TextEditingController(text: widget.settings.geminiKey);
  String result = '';
  bool testing = false;

  Future<void> apply() async {
    final s = widget.settings;
    s.server = server.text;
    s.token = token.text;
    s.geminiKey = key.text;
    if (!s.hasKey) s.engine = 'free';
    await s.save();
  }

  Future<void> test() async {
    setState(() { testing = true; result = ''; });
    await apply();
    try {
      final j = await Api(widget.settings).ping();
      setState(() => result = j['ffmpeg'] == true ? '✔ ភ្ជាប់បាន' : '⚠ ភ្ជាប់បាន តែ server គ្មាន ffmpeg');
    } catch (e) {
      setState(() => result = '✖ $e');
    }
    setState(() => testing = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('⚙ Settings')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Server (កុំព្យូទ័រ ឬ Colab ដែលរត់ server.py)', style: TextStyle(color: Colors.white70)),
        const SizedBox(height: 8),
        TextField(controller: server, keyboardType: TextInputType.url,
            decoration: const InputDecoration(hintText: 'http://192.168.1.2:8765')),
        const SizedBox(height: 12),
        TextField(controller: token, obscureText: true,
            decoration: const InputDecoration(labelText: 'Token (បើ server កំណត់ KD_TOKEN)')),
        const SizedBox(height: 20),
        const Text('Gemini API Key (មិនចាំបាច់ — ប្រើ Gemini បកប្រែឆ្លាតជាង)', style: TextStyle(color: Colors.white70)),
        const SizedBox(height: 8),
        TextField(controller: key, obscureText: true, decoration: const InputDecoration(labelText: 'API Key')),
        const SizedBox(height: 20),
        Row(children: [
          Expanded(child: FilledButton.tonal(onPressed: testing ? null : test, child: const Text('សាកល្បងការភ្ជាប់'))),
          const SizedBox(width: 12),
          Expanded(child: FilledButton(
            onPressed: () async { await apply(); if (context.mounted) Navigator.pop(context, true); },
            child: const Text('រក្សាទុក'),
          )),
        ]),
        const SizedBox(height: 16),
        if (testing) const LinearProgressIndicator(),
        if (result.isNotEmpty) Text(result),
      ]),
    );
  }
}
