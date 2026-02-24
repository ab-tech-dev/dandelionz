import logging

logger = logging.getLogger(__name__)


def dispatch_task(task, *args, fallback_sync=True, **kwargs):
    """
    Try to enqueue a Celery task; optionally fall back to in-process execution.
    Returns True when queued or sync execution succeeds, else False.
    """
    try:
        task.delay(*args, **kwargs)
        return True
    except Exception as queue_error:
        logger.error(
            "Failed to queue task %s with args=%s kwargs=%s: %s",
            getattr(task, "name", str(task)),
            args,
            kwargs,
            queue_error,
            exc_info=True,
        )
        if not fallback_sync:
            return False

    try:
        result = task.apply(args=args, kwargs=kwargs)
        if getattr(result, "failed", lambda: False)():
            logger.error(
                "Fallback execution failed for task %s: %s",
                getattr(task, "name", str(task)),
                getattr(result, "result", None),
            )
            return False
        return True
    except Exception as sync_error:
        logger.error(
            "Fallback execution crashed for task %s: %s",
            getattr(task, "name", str(task)),
            sync_error,
            exc_info=True,
        )
        return False
