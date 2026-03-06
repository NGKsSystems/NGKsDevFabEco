#include "main_window.h"

#include <QApplication>
#include <QTimer>

int main(int argc, char* argv[]) {
    QApplication app(argc, argv);
    MainWindow w;
    w.show();

    QTimer::singleShot(200, &app, &QCoreApplication::quit);
    return app.exec();
}
