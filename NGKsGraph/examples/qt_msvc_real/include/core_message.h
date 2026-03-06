#pragma once

#include <QObject>
#include <QString>

class CoreMessage : public QObject {
    Q_OBJECT
public:
    explicit CoreMessage(QObject* parent = nullptr);
    QString text() const;

signals:
    void ping(QString value);
};
