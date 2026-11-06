import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_frontend/main.dart';

void main() {
  testWidgets('VideoCapureApp initial render test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const VideoCapureApp());
    await tester.pump();

    // Verify title and main UI components are present
    expect(find.text('Tab Video Capture'), findsWidgets);
    expect(find.text('How to Capture'), findsOneWidget);
    expect(find.text('Recorded Videos'), findsOneWidget);
  });
}
