function taipeiParts(ms) {
  const d = new Date(ms);

  const parts =
    new Intl.DateTimeFormat(
      "en-US",
      {
        timeZone:
          "Asia/Taipei",
        year:
          "numeric",
        month:
          "2-digit",
        day:
          "2-digit",
        hour:
          "2-digit",
        minute:
          "2-digit",
        hourCycle:
          "h23",
        weekday:
          "short"
      }
    ).formatToParts(d);

  const get = type =>
    parts.find(
      x =>
        x.type === type
    )?.value || "";

  const weekdayMap = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6
  };

  return {
    year:
      Number(
        get("year")
      ),

    month:
      Number(
        get("month")
      ),

    day:
      Number(
        get("day")
      ),

    hour:
      Number(
        get("hour")
      ),

    minute:
      Number(
        get("minute")
      ),

    weekday:
      weekdayMap[
        get("weekday")
      ]
  };
}


function isTime(
  t,
  h,
  m
) {
  return (
    t.hour === h &&
    t.minute === m
  );
}


function isWeekday(t) {
  return (
    t.weekday >= 1 &&
    t.weekday <= 5
  );
}


async function dispatch(
  env,
  eventType,
  scheduledTime
) {
  const url =
    `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/dispatches`;

  const response =
    await fetch(
      url,
      {
        method:
          "POST",

        headers: {
          "Accept":
            "application/vnd.github+json",

          "Authorization":
            `Bearer ${env.GITHUB_TOKEN}`,

          "X-GitHub-Api-Version":
            "2022-11-28",

          "User-Agent":
            "tw-market-cloudflare-scheduler"
        },

        body:
          JSON.stringify({
            event_type:
              eventType,

            client_payload: {
              source:
                "cloudflare-cron",

              scheduled_time:
                new Date(
                  scheduledTime
                ).toISOString()
            }
          })
      }
    );

  if (
    !response.ok
  ) {
    const body =
      await response.text();

    throw new Error(
      `${eventType} dispatch failed: ${response.status} ${body}`
    );
  }

  console.log(
    "dispatch success:",
    eventType,
    new Date(
      scheduledTime
    ).toISOString()
  );
}


function jobsForTime(t) {
  const jobs = [];

  /*
    ==========================================
    市場熱力圖
    台灣平日 09:00～13:55
    每 5 分鐘
    ==========================================
  */

  if (
    isWeekday(t) &&
    t.hour >= 9 &&
    t.hour <= 13 &&
    t.minute % 5 === 0
  ) {
    jobs.push(
      "heatmap"
    );
  }


  /*
    ==========================================
    每日收盤資料 + AI 選股
    台灣 18:00
    台灣 18:20 備援
    ==========================================
  */

  if (
    isTime(
      t,
      18,
      0
    ) ||
    isTime(
      t,
      18,
      20
    )
  ) {
    jobs.push(
      "daily_close"
    );
  }


  /*
    ==========================================
    自結公布

    平日 22:00
    次日 08:00

    08:00：
    週二～週六
    ==========================================
  */

  if (
    isWeekday(t) &&
    isTime(
      t,
      22,
      0
    )
  ) {
    jobs.push(
      "self_reports"
    );
  }


  if (
    t.weekday >= 2 &&
    t.weekday <= 6 &&
    isTime(
      t,
      8,
      0
    )
  ) {
    jobs.push(
      "self_reports"
    );
  }


  /*
    ==========================================
    融資／借券

    平日 21:20
    平日 22:45
    ==========================================
  */

  if (
    isWeekday(t) &&
    (
      isTime(
        t,
        21,
        20
      ) ||
      isTime(
        t,
        22,
        45
      )
    )
  ) {
    jobs.push(
      "margin_lending"
    );
  }


  /*
    ==========================================
    大戶籌碼

    週六 17:00
    週六 17:20 補跑
    ==========================================
  */

  if (
    t.weekday === 6 &&
    (
      isTime(
        t,
        17,
        0
      ) ||
      isTime(
        t,
        17,
        20
      )
    )
  ) {
    jobs.push(
      "holders"
    );
  }


  /*
    ==========================================
    月營收

    每月 1～15 日

    10:00
    14:00
    18:00
    21:00
    ==========================================
  */

  if (
    t.day >= 1 &&
    t.day <= 15 &&
    (
      isTime(
        t,
        10,
        0
      ) ||
      isTime(
        t,
        14,
        0
      ) ||
      isTime(
        t,
        18,
        0
      ) ||
      isTime(
        t,
        21,
        0
      )
    )
  ) {
    jobs.push(
      "monthly_revenue"
    );
  }


  /*
    避免同一時間重複加入相同 job
  */

  return [
    ...new Set(
      jobs
    )
  ];
}


export default {

  /*
    手動開 Worker 網址時
    可以用 /health 確認 Worker 是否活著
  */

  async fetch(
    request,
    env
  ) {
    const url =
      new URL(
        request.url
      );

    if (
      url.pathname ===
      "/health"
    ) {
      return Response.json({
        ok:
          true,

        service:
          "tw-market-scheduler",

        owner:
          env.GITHUB_OWNER,

        repo:
          env.GITHUB_REPO
      });
    }

    return new Response(
      "tw-market-scheduler",
      {
        status:
          200
      }
    );
  },


  /*
    Cloudflare Cron Trigger
    每 5 分鐘進來一次

    再由 jobsForTime()
    判斷現在該跑哪一個 GitHub Action
  */

  async scheduled(
    controller,
    env,
    ctx
  ) {
    const taipei =
      taipeiParts(
        controller
          .scheduledTime
      );

    console.log(
      "Taipei time:",
      taipei
    );


    const jobs =
      jobsForTime(
        taipei
      );


    if (
      !jobs.length
    ) {
      console.log(
        "No scheduled job for this slot"
      );

      return;
    }


    console.log(
      "Jobs:",
      jobs
    );


    for (
      const job
      of jobs
    ) {
      ctx.waitUntil(
        dispatch(
          env,
          job,
          controller
            .scheduledTime
        )
      );
    }
  }
};
