      .stock-flow-table-wrap{
        margin-top:14px;
        overflow:auto;
        border:1px solid var(--line);
        border-radius:16px;
        background:var(--card);
        -webkit-overflow-scrolling:touch
      }

      .stock-flow-table{
        width:100%;
        min-width:570px;
        border-collapse:separate;
        border-spacing:0
      }

      .stock-flow-table th,
      .stock-flow-table td{
        padding:12px 10px;
        border-bottom:1px solid var(--line);
        text-align:right;
        white-space:nowrap;
        font-size:11px;
        font-variant-numeric:tabular-nums
      }

      .stock-flow-table th{
        background:var(--soft);
        color:var(--muted);
        font-size:10px;
        font-weight:900;
        letter-spacing:.02em
      }

      .stock-flow-table th:first-child,
      .stock-flow-table td:first-child{
        text-align:left;
        padding-left:14px
      }

      .stock-flow-table th:last-child,
      .stock-flow-table td:last-child{
        padding-right:14px;
        font-weight:900
      }
