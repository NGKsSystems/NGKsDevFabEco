#pragma once

#include <QMainWindow>

class CoreMessage;

namespace Ui {
class MainWindow;
}

class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow() override;

public slots:
    void onPing(const QString& value);

private:
    Ui::MainWindow* ui;
    CoreMessage* core;
};
