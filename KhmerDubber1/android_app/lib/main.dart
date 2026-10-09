import 'package:flutter/material.dart';
import 'api.dart';
import 'home.dart';

void main() => runApp(const DubberApp());

class DubberApp extends StatelessWidget {
  const DubberApp({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(seedColor: const Color(0xFF7C5CFF), brightness: Brightness.dark);
    return MaterialApp(
      title: 'Dubber ខ្មែរ',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: scheme,
        scaffoldBackgroundColor: const Color(0xFF0F0F14),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF1F1F2B),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
        ),
      ),
      home: FutureBuilder<Settings>(
        future: Settings.load(),
        builder: (context, snap) {
          if (!snap.hasData) return const Scaffold(body: Center(child: CircularProgressIndicator()));
          return HomeScreen(settings: snap.data!);
        },
      ),
    );
  }
}
