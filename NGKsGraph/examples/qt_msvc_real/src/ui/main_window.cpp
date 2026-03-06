#include "main_window.h"

#include "core_message.h"
#include "ui_mainwindow.h"

#include <QFile>
#include <QLabel>

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent),
      ui(new Ui::MainWindow()),
      core(new CoreMessage(this)) {
    ui->setupUi(this);
    QObject::connect(core, &CoreMessage::ping, this, &MainWindow::onPing);
    emit core->ping(core->text());

    QFile resourceText(":/assets/message.txt");
    if (resourceText.open(QIODevice::ReadOnly | QIODevice::Text)) {
        const QString line = QString::fromUtf8(resourceText.readAll()).trimmed();
        ui->resourceLabel->setText(line);
    } else {
        ui->resourceLabel->setText(QStringLiteral("resource read failed"));
    }

    ui->iconLabel->setText(QStringLiteral("icon resource skipped"));
}

MainWindow::~MainWindow() {
    delete ui;
}

void MainWindow::onPing(const QString& value) {
    ui->messageLabel->setText(value);
}
