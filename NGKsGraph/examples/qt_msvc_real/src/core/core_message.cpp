#include "core_message.h"

CoreMessage::CoreMessage(QObject* parent) : QObject(parent) {
}

QString CoreMessage::text() const {
    return QStringLiteral("Hello from libcore");
}
