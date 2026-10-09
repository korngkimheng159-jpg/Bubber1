import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

const languages = [
  'Khmer', 'English', 'Chinese', 'Thai', 'Vietnamese', 'Japanese', 'Korean',
  'French', 'Spanish', 'German', 'Russian', 'Indonesian', 'Hindi', 'Arabic',
];

class Settings {
  String server, token, geminiKey, src, tgt, engine, stt, whisper;
  bool fast;                                    // ⚡ fast mode: Gemini Lite + short wording

  Settings({
    required this.server,
    required this.token,
    required this.geminiKey,
    required this.src,
    required this.tgt,
    required this.engine,
    required this.stt,
    required this.whisper,
    this.fast = false,
  });

  bool get hasKey => geminiKey.trim().length > 8;

  static Future<Settings> load() async {
    final p = await SharedPreferences.getInstance();
    return Settings(
      server: p.getString('server') ?? 'http://192.168.1.2:8765',
      token: p.getString('token') ?? '',
      geminiKey: p.getString('gemini') ?? '',
      src: p.getString('src') ?? 'Chinese',
      tgt: p.getString('tgt') ?? 'Khmer',
      engine: p.getString('engine') ?? 'free',
      stt: p.getString('stt') ?? 'whisper',
      whisper: p.getString('whisper') ?? 'small',
      fast: p.getBool('fast') ?? false,
    );
  }

  Future<void> save() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('server', server.trim());
    await p.setString('token', token.trim());
    await p.setString('gemini', geminiKey.trim());
    await p.setString('src', src);
    await p.setString('tgt', tgt);
    await p.setString('engine', engine);
    await p.setString('stt', stt);
    await p.setString('whisper', whisper);
    await p.setBool('fast', fast);
  }
}

class Seg {
  double start, end;
  String src, text, gender;
  Seg({required this.start, required this.end, required this.src, required this.text, required this.gender});

  factory Seg.fromJson(Map<String, dynamic> j) => Seg(
        start: (j['start'] as num).toDouble(),
        end: (j['end'] as num).toDouble(),
        src: (j['src'] ?? '') as String,
        text: (j['text'] ?? '') as String,
        gender: (j['gender'] ?? 'female') as String,
      );

  Map<String, dynamic> toJson() => {'start': start, 'end': end, 'src': src, 'text': text, 'gender': gender};
}

class ApiException implements Exception {
  final String msg;
  ApiException(this.msg);
  @override
  String toString() => msg;
}

class Api {
  final Settings s;
  Api(this.s);

  Uri _u(String path) => Uri.parse(s.server.trim().replaceAll(RegExp(r'/+$'), '') + path);
  Map<String, String> get _h => s.token.trim().isEmpty ? {} : {'X-Token': s.token.trim()};

  dynamic _json(http.Response r) {
    if (r.statusCode >= 400) {
      var m = r.body;
      try {
        m = jsonDecode(utf8.decode(r.bodyBytes))['detail'].toString();
      } catch (_) {}
      throw ApiException('${r.statusCode}: $m');
    }
    return jsonDecode(utf8.decode(r.bodyBytes));
  }

  Future<Map<String, dynamic>> ping() async {
    try {
      final r = await http.get(_u('/api/ping'), headers: _h).timeout(const Duration(seconds: 6));
      return Map<String, dynamic>.from(_json(r) as Map);
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('ភ្ជាប់ server មិនបាន — ពិនិត្យ URL និង Wi-Fi តែមួយ');
    }
  }

  Future<String> createJob(String path) async {
    try {
      final req = http.MultipartRequest('POST', _u('/api/jobs'));
      req.headers.addAll(_h);
      req.fields.addAll({
        'src_lang': s.src,
        'tgt_lang': s.tgt,
        'engine': s.engine,
        'stt': s.stt,
        'whisper_size': s.whisper,
        'gemini_key': s.geminiKey.trim(),
        'fast': (s.fast && s.hasKey) ? '1' : '',
      });
      req.files.add(await http.MultipartFile.fromPath('video', path));
      final r = await http.Response.fromStream(await req.send());
      return (_json(r) as Map)['id'] as String;
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('Upload មិនបាន — ពិនិត្យការភ្ជាប់ server');
    }
  }

  Future<Map<String, dynamic>> status(String id) async {
    final r = await http.get(_u('/api/jobs/$id'), headers: _h).timeout(const Duration(seconds: 15));
    return Map<String, dynamic>.from(_json(r) as Map);
  }

  Future<void> render(String id, List<Seg> segs,
      {required double speed, required String fit, required bool keepBg, required int res}) async {
    final r = await http.post(
      _u('/api/jobs/$id/render'),
      headers: {..._h, 'Content-Type': 'application/json'},
      body: jsonEncode({
        'segments': segs.map((e) => e.toJson()).toList(),
        'speed': speed,
        'fit': fit,
        'keep_original_bg': keepBg,
        'gemini_key': s.geminiKey.trim(),
        'resolution': res,
      }),
    );
    _json(r);
  }

  Future<String> download(String id) async {
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/dub_$id.mp4');
    final req = http.Request('GET', _u('/api/jobs/$id/video'))..headers.addAll(_h);
    final resp = await req.send();
    if (resp.statusCode >= 400) throw ApiException('Download ${resp.statusCode}');
    await resp.stream.pipe(f.openWrite());
    return f.path;
  }
}
