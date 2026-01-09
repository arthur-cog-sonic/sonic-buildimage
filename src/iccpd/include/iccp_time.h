/*
 * iccp_time.h
 *
 * Y2K38 Safety Header for ICCPD
 *
 * This header provides compile-time checks and helper functions to ensure
 * that the system is using 64-bit time_t to prevent timestamp overflow
 * on January 19, 2038.
 *
 * Copyright(c) 2024 Broadcom.
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms and conditions of the GNU General Public License,
 * version 2, as published by the Free Software Foundation.
 */

#ifndef ICCP_TIME_H_
#define ICCP_TIME_H_

#include <time.h>
#include <stdint.h>

/*
 * Y2K38 Compile-Time Check
 *
 * Ensure that time_t is at least 64-bit to prevent timestamp overflow
 * on January 19, 2038 (Unix timestamp 2147483647).
 *
 * On 64-bit Linux systems, time_t is typically 64-bit.
 * On 32-bit systems, time_t may be 32-bit which will cause overflow.
 *
 * If this assertion fails, the system needs to be compiled with
 * -D_TIME_BITS=64 -D_FILE_OFFSET_BITS=64 flags or use a 64-bit platform.
 */
_Static_assert(sizeof(time_t) >= 8,
    "Y2K38: time_t must be at least 64-bit to prevent timestamp overflow. "
    "Compile with -D_TIME_BITS=64 -D_FILE_OFFSET_BITS=64 or use a 64-bit platform.");

/*
 * Y2K38 Boundary Constants
 */
#define Y2K38_BOUNDARY_TIMESTAMP 2147483647LL  /* 2038-01-19 03:14:07 UTC */
#define Y2K38_WARNING_THRESHOLD  2145916800LL  /* 2038-01-01 00:00:00 UTC */

/*
 * iccp_time_is_y2k38_safe
 *
 * Check if the current system time is before the Y2K38 warning threshold.
 * This can be used for runtime validation.
 *
 * Returns: 1 if safe (before 2038), 0 if approaching Y2K38 boundary
 */
static inline int iccp_time_is_y2k38_safe(void)
{
    time_t now = time(NULL);
    return (now < Y2K38_WARNING_THRESHOLD) ? 1 : 0;
}

/*
 * iccp_time_get_safe
 *
 * Get the current time with Y2K38 safety check.
 * This is a wrapper around time() that ensures the returned value
 * is valid for 64-bit operations.
 *
 * Returns: Current time as time_t (64-bit on properly configured systems)
 */
static inline time_t iccp_time_get_safe(void)
{
    return time(NULL);
}

#endif /* ICCP_TIME_H_ */
